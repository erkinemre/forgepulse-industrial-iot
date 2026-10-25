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
  let previous='';
  const seen=new Set();
  const seconds=Number(process.env.CAMERA_DEMO_SECONDS||60);
  for(let i=0;i<seconds;i++) {
    const value=(await section.locator('p').innerText()).replace(/\s+/g,' ').trim();
    const label=value.split(' · ').slice(0,2).join(' · ');
    if(label!==previous){console.log('UI_CAMERA',label,value);previous=label;}
    if(label.startsWith('Bağlı · ')) seen.add(label);
    await delay(1000);
  }
  const expected=['Bağlı · Normal çalışıyor','Bağlı · Yorgun','Bağlı · Kişi yok'];
  const missing=expected.filter(label=>!seen.has(label));
  if(missing.length) throw Error('Missing live camera UI classes: '+missing.join(', '));
  console.log('CAMERA_UI_THREE_CLASSES_OK');
} finally {await browser.close();}
