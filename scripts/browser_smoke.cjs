// Optional real-browser acceptance test. Uses only a fresh temporary database.
// Supply PLAYWRIGHT_MODULE (or install Playwright outside runtime dependencies),
// PYTHON_EXECUTABLE, BROWSER_EXECUTABLE, and optionally SMOKE_OUTPUT_DIR.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');
const { spawn, execFileSync } = require('node:child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const root = path.resolve(__dirname, '..');
  const data = fs.mkdtempSync(path.join(os.tmpdir(), 'store-sale-ui-'));
  const out = process.env.SMOKE_OUTPUT_DIR || data;
  fs.mkdirSync(out, {recursive:true});
  const server = net.createServer();
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const port = server.address().port;
  await new Promise(resolve=>server.close(resolve));
  const origin=`http://127.0.0.1:${port}`;
  const python=process.env.PYTHON_EXECUTABLE || 'python';
  const app=spawn(python,['-u','-c',"import os; print('Starting isolated smoke server',os.environ.get('STORE_DATA_DIR'),os.environ.get('STORE_PORT'),flush=True); from app.__main__ import main; main()",'--no-browser'],{cwd:root,env:{...process.env,STORE_DATA_DIR:data,STORE_PORT:String(port)},windowsHide:true,stdio:['ignore','pipe','pipe']});
  let log=''; app.stdout.on('data',b=>log+=b); app.stderr.on('data',b=>log+=b);
  let browser;
  try {
    let ready=false; let lastError=''; console.log('Starting browser smoke at '+origin+' with '+data);
    for(let n=0;n<150;n++) {
      if(app.exitCode!==null) throw Error(log);
      try { const r=await fetch(origin+'/health'); if(r.ok) {ready=true;break;} lastError=String(r.status); } catch(e) {lastError=String(e);}
      await new Promise(r=>setTimeout(r,100));
    }
    assert(ready,log+'; last connection: '+lastError); console.log('Isolated server ready');
    browser=await chromium.launch({headless:true,executablePath:process.env.BROWSER_EXECUTABLE});
    const context=await browser.newContext({viewport:{width:1360,height:1000}});
    const external=[];
    await context.route('**/*',route=>{
      if(new URL(route.request().url()).origin!==origin) {external.push(route.request().url());return route.abort();}
      return route.continue();
    });
    const page=await context.newPage();
    const errors=[];page.on('pageerror',e=>errors.push(String(e)));
    async function submit(form) {await Promise.all([page.waitForNavigation(),form.locator('button').click()]);}
    async function fill(form,values) {for(const [key,value] of Object.entries(values)) await form.locator(`[name="${key}"]`).fill(value);}
    await page.goto(origin+'/setup');
    let form=page.locator('form[action="/setup"]');
    await fill(form,{username:'browser-manager',password:'synthetic-password-only'});await submit(form);
    form=page.locator('form[action="/login"]');
    await fill(form,{username:'browser-manager',password:'synthetic-password-only'});await submit(form);
    form=page.locator('form[action="/products"]');
    await fill(form,{sku:'spice',name:'ادویه آزمایشی',price:'15000',basis:'1'});
    await form.locator('[name="kind"]').selectOption('weight');await form.locator('[name="basis_unit"]').selectOption('kg');await submit(form);
    form=page.locator('form[action="/opening"]');
    await fill(form,{qty:'8',value:'80000',reason:'synthetic browser fixture'});
    await form.locator('[name="qty_unit"]').selectOption('kg');await submit(form);
    form=page.locator('form[action="/products"]');
    await fill(form,{sku:'counted',name:'بسته آزمایشی',price:'100',basis:'1'});await submit(form);
    form=page.locator('form[action="/opening"]');await form.locator('[name="product_id"]').selectOption('2');
    await fill(form,{qty:'3',value:'150',reason:'synthetic counted stock'});await form.locator('[name="qty_unit"]').selectOption('count');await submit(form);
    await page.goto(origin+'/checkout');await submit(page.locator('form[action="/carts"]'));
    const cart=page.url();
    form=page.locator('form').filter({has:page.locator('input[name="product_id"][value="1"]')});
    await fill(form,{qty:'0.25'});await form.locator('[name="unit"]').selectOption('kg');await submit(form);
    form=page.locator('form').filter({has:page.locator('input[name="action"][value="set"]')}).filter({has:page.locator('input[name="product_id"][value="2"]')});
    await fill(form,{qty:'1.5'});await submit(form);
    assert.equal((await page.locator('h1').innerText()),'ثبت انجام نشد');
    await page.getByRole('link',{name:'بازگشت به سبد ذخیره‌شده'}).click();
    form=page.locator('form').filter({has:page.locator('input[name="action"][value="set"]')}).filter({has:page.locator('input[name="product_id"][value="2"]')});
    await fill(form,{qty:'1'});await submit(form);
    await page.screenshot({path:path.join(out,'checkout.png'),fullPage:true});
    let replayed=false;
    await page.route('**/carts/*/post',async route=>{
      const first=await route.fetch({maxRedirects:0});
      const second=await route.fetch({maxRedirects:0});
      assert.equal(first.status(),303);assert.equal(second.status(),303);
      assert.equal(first.headers().location,second.headers().location);replayed=true;
      await route.fulfill({response:second});
    });
    form=page.locator('form[action$="/post"]');await fill(form,{tendered:'4000'});await submit(form);
    assert(replayed);await page.unroute('**/carts/*/post');
    assert((await page.locator('.receipt').innerText()).includes('S-00000001'));
    assert((await page.locator('.receipt').innerText()).includes('150 تومان'));
    const receipt=page.url();await page.reload();await page.goto(cart);assert.equal(page.url(),receipt);
    await page.emulateMedia({media:'print'});await page.screenshot({path:path.join(out,'receipt-print.png'),fullPage:true});await page.emulateMedia({media:'screen'});
    await page.goto(origin+'/sales');form=page.locator('form');await fill(form,{q:'spice'});await submit(form);
    assert.equal(await page.locator('a[href*="/documents/"]').count(),1);
    await page.goto(origin+'/checkout');await submit(page.locator('form[action="/carts"]'));
    const cardCart=page.url();form=page.locator('form').filter({has:page.locator('input[name="product_id"][value="1"]')});await fill(form,{qty:'9000'});await submit(form);
    form=page.locator('form[action$="/post"]');await submit(form);
    assert.equal(await page.locator('h1').innerText(),'ثبت انجام نشد');
    await page.goto(cardCart);form=page.locator('form').filter({has:page.locator('input[name="action"][value="set"]')}).filter({has:page.locator('input[name="product_id"][value="1"]')});await fill(form,{qty:'250'});await submit(form);
    form=page.locator('form[action$="/post"]');await form.locator('[name="method"]').selectOption('manual_card');await submit(form);
    assert((await page.locator('main').innerText()).includes('صریحاً تأیید'));
    await page.goto(cardCart);form=page.locator('form[action$="/post"]');await form.locator('[name="method"]').selectOption('manual_card');await form.locator('[name="confirmed"]').check();await submit(form);
    assert((await page.locator('.receipt').innerText()).includes('کارت — تأیید دستی'));
    await page.goto(origin+'/suppliers');form=page.locator('form[action="/suppliers"]');await fill(form,{name:'تأمین‌کننده آزمایشی',phone:'000'});await submit(form);
    await submit(page.locator('form[action="/carts"]'));
    form=page.locator('form').filter({has:page.locator('input[name="product_id"][value="1"]')});await fill(form,{qty:'2',unit_cost:'20000',basis:'1'});await form.locator('[name="unit"]').selectOption('kg');await form.locator('[name="basis_unit"]').selectOption('kg');await submit(form);
    form=page.locator('form[action$="/post"]');await fill(form,{paid:'10000'});await form.locator('[name="method"]').selectOption('external_transfer');await form.locator('[name="confirmed"]').check();await submit(form);
    assert((await page.locator('main').innerText()).includes('30,000 تومان'));
    form=page.locator('form[action$="/payments"]');await fill(form,{amount:'30000'});await form.locator('[name="method"]').selectOption('external_transfer');await form.locator('[name="confirmed"]').check();await submit(form);
    assert((await page.locator('main').innerText()).includes('مانده بدهی: 0 تومان'));
    await page.goto(origin+'/suppliers');await page.screenshot({path:path.join(out,'suppliers.png'),fullPage:true});
    assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
    const evidence=execFileSync(python,['-c',`import sqlite3,sys,json; c=sqlite3.connect(sys.argv[1]); print(json.dumps({'documents':c.execute('SELECT kind,COUNT(*) FROM documents GROUP BY kind').fetchall(),'payments':c.execute('SELECT method,COUNT(*) FROM payments GROUP BY method').fetchall(),'stock':c.execute('SELECT product_id,qty_base,value_rial FROM stock_balances ORDER BY product_id').fetchall(),'payable':c.execute('SELECT SUM(amount_rial) FROM supplier_entries').fetchone()[0],'integrity':c.execute('PRAGMA integrity_check').fetchone()[0]}))`,path.join(data,'store.sqlite3')],{encoding:'utf8',windowsHide:true});
    const result=JSON.parse(evidence);assert.equal(result.payable,0);assert.equal(result.integrity,'ok');
    assert.deepEqual(result.stock,[[1,9500,1150000],[2,2,1000]]);
    fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({passed:true,dataDir:data,...result},null,2));
    console.log('Browser smoke passed: cash/retry, count rejection, g/kg, insufficient stock, manual card confirmation, receipt reprint/print CSS, history search, part-paid purchase and supplier settlement; no external requests.');
    console.log(evidence);console.log('Evidence: '+out);
  } finally {
    if(browser)await browser.close();app.kill();
    await new Promise(resolve=>{if(app.exitCode!==null)resolve();else app.once('exit',resolve);});
    fs.writeFileSync(path.join(out,'app-log.txt'),log);
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
