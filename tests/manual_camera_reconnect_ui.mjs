// Live acceptance: observe camera stale/disconnected status and recovery in React.
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {resolve} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';

const require=createRequire(import.meta.url);
const {chromium}=require(resolve('web/node_modules/playwright'));
const secret=JSON.parse(readFileSync('work/runtime-secrets.json','utf8'));
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',args:['--no-sandbox']});
try {
  const page=await browser.newPage();
  await page.goto('http://127.0.0.1:5173');
  await page.getByPlaceholder('Kullanıcı',{exact:true}).fill('admin');
  await page.getByPlaceholder('Parola',{exact:true}).fill(secret.admin_password);
  await page.getByRole('button',{name:'Giriş'}).click();
  const section=page.locator('section').filter({has:page.getByRole('heading',{name:'Kamera sınıfı'})});
  await section.waitFor();
  let lost=false, recovered=false, previous='';
  const seconds=Number(process.env.CAMERA_RECONNECT_SECONDS||90);
  for(let i=0;i<seconds;i++) {
    const value=(await section.locator('p').innerText()).replace(/\s+/g,' ').trim();
    const status=value.split(' · ')[0];
    if(status!==previous) {console.log('UI_CAMERA_CONNECTION',status,value); previous=status;}
    if(status==='Kopuk') lost=true;
    if(lost && status==='Bağlı') {recovered=true; break;}
    await delay(1000);
  }
  if(!lost || !recovered) throw Error(`Camera reconnect UI incomplete: lost=${lost} recovered=${recovered}`);
  console.log('CAMERA_UI_RECONNECT_OK');
} finally {await browser.close();}
