const fs = require('node:fs');
const path = require('node:path');
const sharp = require(process.env.POSTER_SHARP_PATH || '/Users/tanghaoyu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp');

const DIR = __dirname;
const SHOTS = path.resolve(DIR, '../mdl-studio');
const W = 1600, H = 4200;
const C = { ink:'#20394D', muted:'#587084', blue:'#137CC1', line:'#D4E2EC', pale:'#ECF5FC', bg:'#F7FAFD', navy:'#17374E' };
const items = [];
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
function rect(x,y,w,h,fill,stroke='none',r=0,sw=1) {
  items.push(`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/>`);
}
function line(x1,y1,x2,y2,color=C.line,sw=1) {
  items.push(`<path d="M${x1} ${y1}L${x2} ${y2}" fill="none" stroke="${color}" stroke-width="${sw}"/>`);
}
function txt(x,y,content,size=24,color=C.ink,weight=400,opts={}) {
  const lines = Array.isArray(content) ? content : [content];
  const lh = opts.lh || size*1.55;
  items.push(`<text x="${x}" y="${y}" font-family="${opts.mono ? 'Menlo,monospace' : 'PingFang SC,Arial,sans-serif'}" font-size="${size}" font-weight="${weight}" fill="${color}"${opts.anchor ? ` text-anchor="${opts.anchor}"` : ''}${opts.spacing ? ` letter-spacing="${opts.spacing}"` : ''}>${lines.map((s,i)=>`<tspan x="${x}" dy="${i ? lh : 0}">${esc(s)}</tspan>`).join('')}</text>`);
}
function image(file,x,y,w,h) {
  const data=fs.readFileSync(file);
  // Some original screenshots have a .png suffix but contain JPEG bytes.
  const mime = data[0]===0xFF && data[1]===0xD8 ? 'image/jpeg' : 'image/png';
  items.push(`<image x="${x}" y="${y}" width="${w}" height="${h}" href="data:${mime};base64,${data.toString('base64')}" preserveAspectRatio="xMidYMid meet"/>`);
}
function arrow(x1,y1,x2,y2,color='#59B3EA',sw=2.5) {
  line(x1,y1,x2,y2,color,sw);
  const a = Math.atan2(y2-y1,x2-x1), s=9;
  const p1=[x2-s*Math.cos(a-.55),y2-s*Math.sin(a-.55)];
  const p2=[x2-s*Math.cos(a+.55),y2-s*Math.sin(a+.55)];
  items.push(`<path d="M${p1.join(' ')}L${x2} ${y2}L${p2.join(' ')}" fill="none" stroke="${color}" stroke-width="${sw}" stroke-linejoin="round"/>`);
}
async function screenshot(name,x,y,w) {
  const file=path.join(SHOTS,name), meta=await sharp(file).metadata();
  const h=meta.height/meta.width*w;
  rect(x-1,y-1,w+2,h+2,'#FFFFFF',C.line,9,2);
  // Embed each captured interface as a single image. UI content is never redrawn.
  image(file,x,y,w,h);
  return {name,original:[meta.width,meta.height],rect:[x,y,w,h]};
}

(async()=>{
  rect(0,0,W,H,C.bg);
  rect(0,0,W,402,'#EDF6FC');
  rect(0,0,12,402,C.blue);
  txt(96,83,'DataSemantic',42,C.ink,700);
  txt(1504,77,'MyCoWork 配套基础设施',21,C.muted,500,{anchor:'end'});
  line(96,112,1504,112,'#D3E6F3');
  txt(96,191,'业务语义建模',62,C.ink,700);
  txt(96,270,'与可验证的查询服务',62,C.ink,700);
  txt(98,328,['为 MyCoWork 行业应用提供模型上下文、SQL 规划与只读执行能力。','把表结构、业务口径与关联关系，沉淀为可复用的语义模型。'],24,C.muted,400,{lh:40});
  image(path.join(DIR,'datasemantic-cow-editorial.png'),1120,123,385,272);

  txt(96,456,'解决什么问题',19,C.blue,600,{spacing:2});
  const advantages = [
    {x:96,n:'01',title:'复杂表结构，统一建模',pain:'表多、字段杂，靠文档反复解释',body:['数据库扫描 / DDL 导入','可视化维护模型、字段与关联']},
    {x:574,n:'02',title:'业务口径，集中沉淀',pain:'同一指标，算法散落在不同代码中',body:['计算字段 / 语义视图','将业务定义沉淀为可复用模型']},
    {x:1052,n:'03',title:'查询逻辑，可查可验',pain:'生成了 SQL，却难复核和追溯',body:['SQL 预览 / 不可变版本','查看规划结果，固定模型哈希']}
  ];
  for(const a of advantages){
    rect(a.x,485,452,220,'#FFFFFF',C.line,10);
    txt(a.x+24,522,a.n,18,C.blue,600,{mono:true});
    txt(a.x+24,566,a.title,27,C.ink,600);
    txt(a.x+24,604,a.pain,20,C.muted);
    txt(a.x+24,647,a.body,21,C.blue,400,{lh:30});
  }

  txt(96,779,'技术架构',34,C.ink,600);
  txt(1504,778,'显式建模 → 查询规划 → 按需执行',21,C.muted,400,{anchor:'end'});
  rect(96,820,1408,413,C.navy,'none',14);
  rect(418,850,822,350,'#1D415B','#3E647E',10);
  txt(442,891,'DataSemantic',28,'#FFFFFF',600);
  txt(1209,887,'HTTP API',16,'#A8C5D8',400,{anchor:'end',mono:true});
  rect(442,918,772,95,'#2B526D','#527D99',7);
  txt(465,954,'MDL Studio',25,'#FFFFFF',600);
  txt(465,990,'模型 · 字段 · 关联 · 计算口径',21,'#D5E7F2');
  txt(1191,957,'校验 / 版本发布',20,'#93D1F7',500,{anchor:'end'});
  txt(1191,987,'不可变模型 + 哈希',17,'#B6D0E1',400,{anchor:'end'});
  arrow(702,1013,702,1068);
  txt(719,1047,'语义模型参与规划',17,'#A9D8F4');
  const steps=[{x:442,w:146,t:'语义 SQL'},{x:621,w:162,t:'规划 /plan'},{x:816,w:146,t:'物理 SQL'},{x:995,w:219,t:'执行 /execute'}];
  for(let i=0;i<steps.length;i++){
    const s=steps[i]; rect(s.x,1074,s.w,70,'#F4F9FC','none',7);
    txt(s.x+s.w/2,1117,s.t,22,C.ink,600,{anchor:'middle'});
    if(i<steps.length-1) arrow(s.x+s.w+7,1109,steps[i+1].x-7,1109);
  }
  rect(126,1038,242,136,'#21455E','#527D99',8);
  txt(247,1080,'宿主业务工具',25,'#FFFFFF',600,{anchor:'middle'});
  txt(247,1116,'MyCoWork / 行业应用',18,'#BBD3E3',400,{anchor:'middle'});
  txt(247,1149,'提供已授权的业务上下文',17,'#BBD3E3',400,{anchor:'middle'});
  arrow(368,1109,435,1109);
  rect(1286,1038,190,136,'#21455E','#527D99',8);
  txt(1381,1080,'业务数据库',25,'#FFFFFF',600,{anchor:'middle'});
  txt(1381,1117,'PostgreSQL',19,'#BBD3E3',400,{anchor:'middle',mono:true});
  txt(1381,1148,'MySQL',19,'#BBD3E3',400,{anchor:'middle',mono:true});
  arrow(1218,1109,1280,1109);
  txt(96,1282,'规划与执行可独立使用；执行按需启用，最终用户权限由宿主落实。',22,C.muted);
  txt(96,1322,'基于 WrenAI Core SDK · 模型上下文接口 · SQL 规划接口 · 可选只读执行接口',19,C.blue);

  txt(96,1418,'从真实界面，看能力如何落地',36,C.ink,600);
  txt(1504,1415,'MDL STUDIO / 实际系统截图',18,C.muted,400,{anchor:'end',spacing:1});

  // 01: Keep the complete screenshot, including the navigation and actual records.
  txt(96,1513,'01',24,C.blue,600,{mono:true});
  txt(96,1571,['模型工作空间','统一管理草稿与发布'],31,C.ink,600,{lh:47});
  txt(96,1698,['按名称、数据库与状态查找模型；','导入已有 MDL，继续编辑；','草稿校验后发布为独立版本。'],23,C.muted,400,{lh:43});
  line(96,1834,373,1834);
  txt(96,1881,'从数据库结构开始',23,C.blue,600);
  txt(96,1928,['支持 PostgreSQL / MySQL 扫描，','也可导入 DDL 辅助创建模型。','生成后补充并复核业务定义。'],21,C.muted,400,{lh:38});
  const manifest=[];
  manifest.push(await screenshot('workspace-list.png',448,1464,1056));
  txt(448,2234,'界面 01  /  模型工作空间：集中管理模型草稿、状态和已发布版本。',20,C.muted);

  line(96,2286,1504,2286);
  txt(96,2358,'02',24,C.blue,600,{mono:true});
  txt(154,2359,'模型关联画布：把连接关系落到具体字段',31,C.ink,600);
  txt(96,2405,'查看字段连线、1 / N 基数与关联条件；支持缩放、平移与关系编辑。',23,C.muted);
  manifest.push(await screenshot('relation-canvas.jpg',96,2443,1408));
  txt(96,3198,'界面 02  /  关联仅来自显式配置；字段连线与基数标注帮助复核连接逻辑。',20,C.muted);

  line(96,3250,1504,3250);
  txt(96,3322,'03',24,C.blue,600,{mono:true});
  txt(154,3323,'语义视图与测试：业务定义可复用，SQL 规划可检查',31,C.ink,600);
  txt(96,3369,'维护查询定义与业务说明，测试视图并检查规划状态、耗时及生成的物理 SQL。',23,C.muted);
  manifest.push(await screenshot('semantic-view-test.jpg',96,3407,1408));

  // Footer is placed below the third viewport, with a clear distinction between planning and execution.
  txt(96,4164,'截图来自仓库中实际运行的 MDL Studio，使用演示 / 验证模型；视图测试验证 SQL 规划，不执行业务查询。',18,C.muted);
  const finalH=4330;
  rect(0,4211,W,finalH-4211,'#EAF3FA');
  txt(96,4261,'DataSemantic',29,C.ink,700);
  txt(96,4300,'语义模型可维护 · 业务口径可复用 · 查询链路可验证',21,C.blue);
  txt(1504,4261,'为 MyCoWork 行业应用补齐数据语义基础设施',21,C.ink,500,{anchor:'end'});
  txt(1504,4300,'WrenAI Core  /  React + Ant Design  /  FastAPI',17,C.muted,400,{anchor:'end'});

  const svg=`<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="${W}" height="${finalH}" viewBox="0 0 ${W} ${finalH}"><rect width="${W}" height="${finalH}" fill="${C.bg}"/>${items.join('\n')}</svg>`;
  fs.writeFileSync(path.join(DIR,'datasemantic-mycowork-long.svg'),svg);
  await sharp(Buffer.from(svg), {density:108}).png().toFile(path.join(DIR,'datasemantic-mycowork-long.png'));
  await sharp(Buffer.from(svg), {density:45}).png().toFile(path.join(DIR,'datasemantic-mycowork-long-preview.png'));
  fs.writeFileSync(path.join(DIR,'datasemantic-long-screenshot-sources.json'),JSON.stringify({screenshots:manifest,uiRedrawn:false,artwork:'datasemantic-cow-editorial.png'},null,2)+'\n');
  console.log(JSON.stringify({width:2400,height:6495,svg:[W,finalH],screenshots:manifest.map(m=>m.name)},null,2));
})();
