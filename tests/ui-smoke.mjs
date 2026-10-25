// Browser smoke: login, live page, and role-specific UI controls.
import {spawn} from 'node:child_process';
import {setTimeout as delay} from 'node:timers/promises';
import {resolve} from 'node:path';
import {createRequire} from 'node:module';
import crypto from 'node:crypto';
const require=createRequire(import.meta.url);
const {chromium}=require(resolve(process.env.BUNDLED_NODE_MODULES||'web/node_modules','playwright'));
const python=process.env.PYTHON_EXECUTABLE||resolve('.venv/Scripts/python.exe');
const apiPort=process.env.UI_TEST_API_PORT||'8100';
const webPort=process.env.UI_TEST_WEB_PORT||'5174';
const apiUrl=`http://127.0.0.1:${apiPort}`;
const webUrl=`http://127.0.0.1:${webPort}`;
const db='work/ui-'+crypto.randomUUID()+'.db';
const root=process.cwd();
const env={...process.env,PYTHONPATH:resolve('work/pydeps')+';'+root,FACTOREDGE_DB:db,ADMIN_PASSWORD:'ui-test-admin-password',INGEST_KEY:'ui-test-key',DISABLE_COLLECTORS:'1',WEB_ORIGIN:webUrl};
const api=spawn(python,['-m','uvicorn','server.app:app','--host','127.0.0.1','--port',apiPort],{cwd:root,env,stdio:'ignore'});
const web=spawn(python,['-m','http.server',webPort,'--bind','127.0.0.1'],{cwd:resolve('web/dist'),env,stdio:'ignore'});
let browser;
try{
  for(let i=0;i<30;i++){try{const r=await fetch(apiUrl+'/openapi.json');if(r.ok)break;}catch{}await delay(200)}
  browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',args:['--no-sandbox']});
  const page=await browser.newPage();
  await page.addInitScript(url=>{window.FACTOREDGE_API=url},apiUrl);
  await page.goto(webUrl);
  await page.getByPlaceholder('Kullanıcı',{exact:true}).fill('admin');
  await page.getByPlaceholder('Parola',{exact:true}).fill('ui-test-admin-password');
  await page.getByRole('button',{name:'Giriş'}).click();
  await page.getByRole('heading',{name:'Mini Akıllı Fabrika'}).waitFor();
  await page.getByRole('heading',{name:'Kullanıcı yönetimi'}).waitFor();
  const token=await page.evaluate(()=>sessionStorage.getItem('token'));
  for(const role of ['engineer','viewer']){
    const r=await fetch(apiUrl+'/api/users',{method:'POST',headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify({username:role,password:'long-test-password',role})});
    if(!r.ok)throw Error('user creation '+r.status);
  }
  for(const role of ['engineer','viewer']){
    await page.getByRole('button',{name:'Çıkış'}).click();
    await page.getByPlaceholder('Kullanıcı',{exact:true}).fill(role);
    await page.getByPlaceholder('Parola',{exact:true}).fill('long-test-password');
    await page.getByRole('button',{name:'Giriş'}).click();
    await page.getByRole('heading',{name:'Mini Akıllı Fabrika'}).waitFor();
    if(await page.getByRole('heading',{name:'Kullanıcı yönetimi'}).count())throw Error(role+' saw user management');
    const save=await page.getByRole('button',{name:'Kaydet'}).count();
    if(role==='engineer'&&save<1)throw Error('engineer lacks device editor');
    if(role==='viewer'&&save!==0)throw Error('viewer saw editor');
  }
  console.log('UI smoke passed: admin, engineer, viewer');
}finally{await browser?.close();api.kill();web.kill();}
