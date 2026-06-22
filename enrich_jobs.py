"""Enrich existing jobs with missing data by visiting detail pages."""
import sqlite3
import asyncio
import re
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "career_agent.db")


async def enrich_jobs():
    """Visit job detail pages and extract missing data."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("Playwright not installed. Run: pip install playwright")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, title, company, location, description, source_url, source, skills_required
        FROM jobs 
        WHERE (description IS NULL OR length(description) < 100 
               OR company = 'Unknown' OR company IS NULL
               OR location = 'Unknown' OR location IS NULL)
        AND source_url IS NOT NULL AND source_url != ''
        LIMIT 100
    """)
    
    jobs = cursor.fetchall()
    print(f"Found {len(jobs)} jobs to enrich")
    
    updated = 0
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        for job_id, title, company, location, description, url, source, skills in jobs:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
                
                new_data = await page.evaluate("""() => {
                    const result = {};
                    
                    const selectors = [
                        '.job-description', '.description__text', '.jobsearch-jobDescriptionText',
                        '.jobDescription', '#jobDescriptionText', '.jd-desc',
                        '[data-testid="jobDescription"]', '.job-details', 'article'
                    ];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.innerText.trim().length > 50) {
                            result.description = el.innerText.trim().substring(0, 5000);
                            break;
                        }
                    }
                    
                    const companySelectors = [
                        '.company_name', '.companyName', '[data-company]',
                        '.employer-name', '.job-details-company-name',
                        '.job-card-container__company-name', '.org-name'
                    ];
                    for (const sel of companySelectors) {
                        const el = document.querySelector(sel);
                        if (el && el.innerText.trim().length > 1) {
                            result.company = el.innerText.trim();
                            break;
                        }
                    }
                    
                    const locationSelectors = [
                        '.job-location', '.companyLocation', '.jobDetailsLocation',
                        '.job-card-container__metadata-item', '.location'
                    ];
                    for (const sel of locationSelectors) {
                        const el = document.querySelector(sel);
                        if (el && el.innerText.trim().length > 1) {
                            result.location = el.innerText.trim();
                            break;
                        }
                    }
                    
                    const expText = document.body?.innerText || '';
                    const expMatch = expText.match(/(\d+[\+]?\s*(?:to|-)\s*\d+\s*years?|\d+\s*years?\s*experience|fresher|entry.?level|junior|senior|experience:\s*\d+)/i);
                    if (expMatch) {
                        result.experience = expMatch[0].substring(0, 100);
                    }
                    
                    const salaryMatch = expText.match(/(₹|INR|Rs\.?|USD|\$|€|£)\s*[\d,]+[\s\-to]+[\d,]+|(?:LPA|lakhs?|per annum|annual|monthly)/i);
                    if (salaryMatch) {
                        result.salary = salaryMatch[0].substring(0, 100);
                    }
                    
                    return result;
                }""")
                
                updates = []
                params = []
                
                if new_data.get('description') and len(new_data['description']) > len(description or ''):
                    updates.append("description = ?")
                    params.append(new_data['description'][:5000])
                
                if new_data.get('company') and (not company or company == 'Unknown'):
                    updates.append("company = ?")
                    params.append(new_data['company'][:500])
                
                if new_data.get('location') and (not location or location == 'Unknown'):
                    updates.append("location = ?")
                    params.append(new_data['location'][:500])
                
                if new_data.get('experience'):
                    updates.append("experience_required = ?")
                    params.append(new_data['experience'][:500])
                
                if new_data.get('salary'):
                    updates.append("salary = ?")
                    params.append(new_data['salary'][:500])
                
                if updates:
                    params.append(job_id)
                    cursor.execute(f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?", params)
                    updated += 1
                    print(f"  Updated job {job_id}: {title[:40]}...")
                
            except Exception as e:
                print(f"  Failed job {job_id}: {str(e)[:50]}")
                continue
        
        await browser.close()
    
    conn.commit()
    conn.close()
    print(f"\nEnriched {updated} jobs with missing data")


if __name__ == "__main__":
    asyncio.run(enrich_jobs())
