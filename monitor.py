import asyncio, os, re, time
from datetime import datetime, timezone
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from db import connect, get_snapshot, upsert_snapshot, alert_recent, mark_alert
from notifier import send_telegram
from parser import parse_table, clean

load_dotenv()
GAME_URLS=[x.strip() for x in os.getenv('GAME_URLS','').split(',') if x.strip()]
POLL_SECONDS=int(os.getenv('POLL_SECONDS','8'))
HEADLESS=os.getenv('HEADLESS','true').lower()!='false'
PAGE_TIMEOUT_MS=int(os.getenv('PAGE_TIMEOUT_MS','30000'))
HANDICAP_MIN_MOVE=float(os.getenv('HANDICAP_MIN_MOVE','1.0'))
TOTAL_MIN_MOVE=float(os.getenv('TOTAL_MIN_MOVE','1.5'))
PRICE_MIN_MOVE=float(os.getenv('PRICE_MIN_MOVE','0.15'))
COOLDOWN=int(os.getenv('ALERT_COOLDOWN_SECONDS','600'))
UA=os.getenv('USER_AGENT','')
TOKEN=os.getenv('TELEGRAM_BOT_TOKEN','')
CHAT=os.getenv('TELEGRAM_CHAT_ID','')

def game_id(url):
    m=re.search(r'/game/(\\d+)',url)
    return m.group(1) if m else url

def alert_text(name,url,market,selection,old,new):
    parts=[f'🚨 {market.upper()} MOVE',name]
    if old.get('line') is not None and new.get('line') is not None and old['line']!=new['line']:
        d=new['line']-old['line']
        parts.append(f'Line: {old["line"]:g} → {new["line"]:g} ({d:+g})')
    if old.get('price') is not None and new.get('price') is not None and old['price']!=new['price']:
        d=new['price']-old['price']
        parts.append(f'Price {selection}: {old["price"]:.3f} → {new["price"]:.3f} ({d:+.3f})')
    parts += [f'Selection: {selection}', f'InfoRadar: {url}']
    return '\\n'.join(parts)

async def click_market(page,label):
    loc=page.get_by_text(label, exact=True)
    for i in range(min(await loc.count(),10)):
        try:
            if await loc.nth(i).is_visible():
                await loc.nth(i).click(timeout=2000)
                await page.wait_for_timeout(350)
                return True
        except Exception:
            pass
    return False

async def game_name(page,url):
    for sel in ['h1','h2','h3']:
        loc=page.locator(sel)
        for i in range(min(await loc.count(),10)):
            txt=clean(await loc.nth(i).inner_text())
            if len(txt)<140 and (' vs ' in txt.lower() or 'santos' in txt.lower()):
                return txt
    return f'Basketball game {game_id(url)}'

async def extract_tables(page):
    out=[]
    tabs=page.locator('table')
    for t in range(await tabs.count()):
        table=tabs.nth(t)
        if not await table.is_visible(): continue
        th=table.locator('th')
        headers=[clean(await th.nth(i).inner_text()) for i in range(await th.count())]
        trs=table.locator('tr')
        rows=[]
        for r in range(1,await trs.count()):
            cells=trs.nth(r).locator('td')
            if await cells.count():
                rows.append([clean(await cells.nth(i).inner_text()) for i in range(await cells.count())])
        if headers and rows: out.append((headers,rows))
    return out

async def process(browser,url,con):
    ctx=await browser.new_context(user_agent=UA or None, viewport={'width':1440,'height':1200})
    page=await ctx.new_page(); page.set_default_timeout(PAGE_TIMEOUT_MS)
    try:
        await page.goto(url,wait_until='domcontentloaded')
        await page.wait_for_timeout(2500)
        name=await game_name(page,url); gid=game_id(url)
        for label,market in [('Handicap','handicap'),('Total','total')]:
            await click_market(page,label)
            await page.wait_for_timeout(200)
            parsed=[]
            for headers,rows in await extract_tables(page):
                parsed += parse_table(headers,rows)
            for item in parsed:
                item.update({'game_url':url,'game_name':name,'market':market,'seen_at':datetime.now(timezone.utc).isoformat()})
                key=f'{gid}:{market}:{item["selection"]}'
                old=get_snapshot(con,key)
                if old:
                    line_move=abs(item['line']-old['line']) if item.get('line') is not None and old.get('line') is not None else 0
                    price_move=abs(item['price']-old['price']) if item.get('price') is not None and old.get('price') is not None else 0
                    threshold=HANDICAP_MIN_MOVE if market=='handicap' else TOTAL_MIN_MOVE
                    if line_move>=threshold or price_move>=PRICE_MIN_MOVE:
                        dedupe=f'{key}:{old.get("line")}:{item.get("line")}:{old.get("price")}:{item.get("price")}'
                        now=time.time()
                        if not alert_recent(con,dedupe,now,COOLDOWN):
                            msg=alert_text(name,url,market,item['selection'],old,item)
                            print(msg); send_telegram(TOKEN,CHAT,msg); mark_alert(con,dedupe,now)
                upsert_snapshot(con,key,item)
    except PlaywrightTimeoutError:
        print(f'Timeout: {url}')
    except Exception as exc:
        print(f'Error: {url}: {exc}')
    finally:
        await ctx.close()

async def main():
    if not GAME_URLS: raise SystemExit('Set GAME_URLS in .env')
    con=connect()
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=HEADLESS)
        while True:
            for url in GAME_URLS:
                await process(browser,url,con)
            await asyncio.sleep(POLL_SECONDS)

if __name__=='__main__': asyncio.run(main())
