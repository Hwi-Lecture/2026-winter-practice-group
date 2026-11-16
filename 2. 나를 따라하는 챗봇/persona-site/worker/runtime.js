const INDEX_HTML = __INDEX_HTML__;
const ADMIN_HTML = __ADMIN_HTML__;
const P = __PROMPTS__;

const roomRE = /^[a-z0-9][a-z0-9_-]{1,29}$/;
const idRE = /^[a-zA-Z0-9-]{8,64}$/;
const models = ["claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"];
const cleanRoom = (v) => { const x = String(v || "").trim().toLowerCase(); return roomRE.test(x) ? x : null; };
const cleanId = (v) => { const x = String(v || "").trim(); return idRE.test(x) ? x : null; };
const cleanNick = (v) => String(v || "").replace(/[\r\n]+/g, " ").trim().slice(0, 20);
const cleanText = (v, n) => String(v || "").trim().slice(0, n);
const base = (r) => `rooms/${r}`;
const response = (data, status=200) => new Response(JSON.stringify(data), {status, headers:{"content-type":"application/json; charset=utf-8", "cache-control":"no-store"}});
const fail = (status, error) => response({error}, status);
const getJSON = async (env, key) => { try { const obj=await env.BUCKET.get(key); return obj ? await obj.json() : null; } catch { return null; } };
const putJSON = async (env, key, value) => env.BUCKET.put(key, JSON.stringify(value), {httpMetadata:{contentType:"application/json"}});
async function listKeys(env, prefix) { const out=[]; let cursor; do { const page=await env.BUCKET.list({prefix,cursor,limit:1000}); out.push(...page.objects.map(x=>x.key)); cursor=page.truncated?page.cursor:undefined; } while(cursor); return out; }
async function getMeta(env,r) { return (await getJSON(env,`${base(r)}/meta.json`)) || {distributed:false}; }
async function ids(env,r,kind) { const p=`${base(r)}/${kind}/`; return (await listKeys(env,p)).map(x=>x.slice(p.length).replace(/\.json$/,"")); }
const shuffle = (a) => { const x=a.slice(); for(let i=x.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[x[i],x[j]]=[x[j],x[i]];} return x; };
function derange(a) { for(let i=0;i<200;i++){const p=shuffle(a);if(p.every((x,j)=>x!==a[j]))return p;} const p=shuffle(a);return p.map((_,i)=>p[(i+1)%p.length]); }
async function assignLeftovers(env,r) {
  const owners=await ids(env,r,"mem"), assigned=await ids(env,r,"asg"), pending=owners.filter(x=>!assigned.includes(x));
  if(!pending.length)return {assigned:0};
  if(!assigned.length){if(owners.length<2)return {assigned:0,error:"제출한 사람이 2명 이상이어야 배분할 수 있어요."};const perm=derange(owners),at=Date.now();await Promise.all(owners.map((id,i)=>putJSON(env,`${base(r)}/asg/${id}.json`,{receiver:id,owner:perm[i],at})));return {assigned:owners.length};}
  const counts=Object.fromEntries(owners.map(x=>[x,0]));
  for(const id of assigned){const a=await getJSON(env,`${base(r)}/asg/${id}.json`);if(a&&counts[a.owner]!==undefined)counts[a.owner]++;}
  let n=0;for(const id of shuffle(pending)){const c=owners.filter(x=>x!==id);if(!c.length)continue;const min=Math.min(...c.map(x=>counts[x]));const owner=shuffle(c.filter(x=>counts[x]===min))[0];counts[owner]++;await putJSON(env,`${base(r)}/asg/${id}.json`,{receiver:id,owner,at:Date.now()});n++;}return {assigned:n};
}
async function stats(env,r){const [m,a,n,meta]=await Promise.all([ids(env,r,"mem"),ids(env,r,"asg"),ids(env,r,"note"),getMeta(env,r)]);return{submitted:m.length,assigned:a.length,notes:n.length,distributed:!!meta.distributed};}
async function claude(env, body) {
  if(!env.ANTHROPIC_API_KEY)throw Object.assign(new Error("서버에 Anthropic API 키가 설정되지 않았어요."),{status:503});
  let r;try{r=await fetch("https://api.anthropic.com/v1/messages",{method:"POST",headers:{"content-type":"application/json","x-api-key":env.ANTHROPIC_API_KEY,"anthropic-version":"2023-06-01"},body:JSON.stringify(body)});}catch{throw Object.assign(new Error("Anthropic 서버에 연결하지 못했어요."),{status:502});}
  const d=await r.json().catch(()=>({}));if(!r.ok){const e=Object.assign(new Error(d?.error?.message||"알 수 없는 오류"),{status:r.status});throw e;}return d;
}
function describeError(e){if(e.status===401||e.status===403)return[401,"서버의 Anthropic API 키가 올바르지 않거나 권한이 없어요."];if(e.status===429)return[429,"요청이 몰리고 있어요. 잠시 뒤 다시 시도해 주세요."];if(e.status===404)return[400,"선택한 모델을 사용할 수 없어요."];return[e.status>=400&&e.status<600?e.status:500,"AI 호출 오류: "+e.message];}
const textOf = (c) => (c||[]).filter(x=>x.type==="text").map(x=>x.text).join("").trim();
const jsonBody = async (req) => { try{return await req.json();}catch{return{};} };

async function handleChat(req,env){
 if(req.method!=="POST")return fail(405,"POST만 가능해요.");const b=await jsonBody(req),room=cleanRoom(b.room),id=cleanId(b.id);
 if(!room||!id)return fail(400,"수업 코드나 접속 정보가 올바르지 않아요.");const model=models.includes(b.model)?b.model:models[0],mode=b.mode==="own"?"own":b.mode==="persona"?"persona":"collect",action=["greet","chat","refresh"].includes(b.action)?b.action:null;
 if(!action||((mode==="persona"||mode==="own")&&action==="refresh"))return fail(400,"요청 형식이 올바르지 않아요.");
 const all=Array.isArray(b.messages)?b.messages.filter(m=>m&&(m.role==="user"||m.role==="assistant")&&typeof m.content==="string"&&m.content.trim()).map(m=>({role:m.role,content:m.content.slice(0,2000)})):[];
 const userCount=all.filter(m=>m.role==="user").length;let msgs=all.slice(-40);if(action!=="greet"&&!msgs.length)return fail(400,"대화 내용이 비어 있어요.");if(action==="chat"&&msgs.at(-1).role!=="user")return fail(400,"요청 형식이 올바르지 않아요.");if(action==="greet")msgs=[{role:"user",content:P.START_USER}];else if(msgs[0].role!=="user")msgs.unshift({role:"user",content:P.START_USER});if(action==="refresh")msgs.push({role:"user",content:P.REFRESH_USER});
 try{
  if(mode==="own"){const mem=await getJSON(env,`${base(room)}/mem/${id}.json`);if(!mem)return fail(404,"내 메모리를 찾지 못했어요.");const d=await claude(env,{model,max_tokens:1024,system:P.PERSONA_SYSTEM+mem.memory+(action==="greet"?P.GREET_HINT_PERSONA:""),messages:msgs});return response({reply:textOf(d.content)});}
  if(mode==="persona"){const asg=await getJSON(env,`rooms/${room}/asg/${id}.json`);if(!asg)return fail(403,"아직 배정된 대화 상대가 없어요.");const mem=await getJSON(env,`rooms/${room}/mem/${asg.owner}.json`);if(!mem)return fail(404,"대화 상대의 정보를 찾지 못했어요.");const d=await claude(env,{model,max_tokens:1024,system:P.PERSONA_SYSTEM+mem.memory+(action==="greet"?P.GREET_HINT_PERSONA:""),messages:msgs});const reply=textOf(d.content);if(action==="chat")await putJSON(env,`${base(room)}/persona-chat/${id}.json`,{id,owner:asg.owner,messages:all.concat([{role:"assistant",content:reply}]),at:Date.now()});return response({reply});}
  let memory=String(b.memory||"").slice(0,8000),updated=false;const system=P.COLLECT_SYSTEM+(action==="greet"?P.GREET_HINT_COLLECT:P.collectState(memory,userCount,action==="refresh"));const tools=action==="greet"?undefined:[P.MEMORY_TOOL];let reply="";
  for(let i=0;i<3;i++){const payload={model,max_tokens:4096,system,messages:msgs};if(tools)payload.tools=tools;const d=await claude(env,payload);reply=textOf(d.content)||reply;const uses=(d.content||[]).filter(x=>x.type==="tool_use"&&x.name==="write_memory");if(d.stop_reason!=="tool_use"||!uses.length)break;const results=uses.map(u=>{const content=typeof u.input?.content==="string"?u.input.content.slice(0,8000):"";if(content.trim()){memory=content;updated=true;}return{type:"tool_result",tool_use_id:u.id,content:"saved"};});msgs=msgs.concat([{role:"assistant",content:d.content},{role:"user",content:results}]);}
  if(mode==="collect"&&action==="chat")await putJSON(env,`${base(room)}/chat/${id}.json`,{id,messages:all.concat([{role:"assistant",content:reply}]),at:Date.now()});
  return response({reply:action==="refresh"?"":reply,memory,memoryUpdated:updated});
 }catch(e){const[c,m]=describeError(e);return fail(c,m);}
}
async function routeApi(req,env,url){
 const path=url.pathname;
 if(path==="/api/chat")return handleChat(req,env);
 if(path==="/api/status"){
  if(req.method!=="GET")return fail(405,"GET만 가능해요.");const r=cleanRoom(url.searchParams.get("room")),id=cleanId(url.searchParams.get("id"));if(!r||!id)return fail(400,"수업 코드나 접속 정보가 올바르지 않아요.");const[meta,mem,asg]=await Promise.all([getMeta(env,r),getJSON(env,`${base(r)}/mem/${id}.json`),getJSON(env,`${base(r)}/asg/${id}.json`)]);const note=asg?await getJSON(env,`${base(r)}/note/${asg.owner}__${id}.json`):null;return response({submitted:!!mem,distributed:!!meta.distributed,assigned:!!asg,noteDone:!!note,myNote:note?{impression:note.impression,traits:note.traits}:null});
 }
 if(path==="/api/submit"){
  if(req.method!=="POST")return fail(405,"POST만 가능해요.");const b=await jsonBody(req),r=cleanRoom(b.room),id=cleanId(b.id),memory=cleanText(b.memory,8000);if(!r||!id)return fail(400,"수업 코드나 접속 정보가 올바르지 않아요.");if(memory.length<20)return fail(400,"제출할 메모리가 비어 있어요. 대화를 조금 더 나눠 주세요.");const meta=await getMeta(env,r),prev=await getJSON(env,`${base(r)}/mem/${id}.json`);if(prev&&meta.distributed)return response({ok:true,locked:true});await putJSON(env,`${base(r)}/mem/${id}.json`,{id,nick:cleanNick(b.nick),memory,at:Date.now()});if(meta.distributed)await assignLeftovers(env,r);return response({ok:true,locked:false});
 }
 if(path==="/api/note"){
  if(req.method!=="POST")return fail(405,"POST만 가능해요.");const b=await jsonBody(req),r=cleanRoom(b.room),id=cleanId(b.id);if(!r||!id)return fail(400,"수업 코드나 접속 정보가 올바르지 않아요.");const impression=cleanText(b.impression,1000),traits=cleanText(b.traits,1500);if(impression.length<2||traits.length<2)return fail(400,"소감과 느낀 점을 모두 적어 주세요.");const asg=await getJSON(env,`${base(r)}/asg/${id}.json`);if(!asg)return fail(403,"아직 배정된 대화 상대가 없어요.");await putJSON(env,`${base(r)}/note/${asg.owner}__${id}.json`,{owner:asg.owner,writer:id,nick:cleanNick(b.nick),impression,traits,at:Date.now()});return response({ok:true});
 }
 if(path==="/api/result"){
  if(req.method!=="GET")return fail(405,"GET만 가능해요.");const r=cleanRoom(url.searchParams.get("room")),id=cleanId(url.searchParams.get("id"));if(!r||!id)return fail(400,"수업 코드나 접속 정보가 올바르지 않아요.");const mem=await getJSON(env,`${base(r)}/mem/${id}.json`);if(!mem)return fail(404,"아직 제출한 메모리가 없어요.");const names=await listKeys(env,`${base(r)}/note/${id}__`),notes=(await Promise.all(names.map(n=>getJSON(env,n)))).filter(Boolean).sort((a,b)=>a.at-b.at);const keys=await listKeys(env,`${base(r)}/persona-chat/`),chats=(await Promise.all(keys.map(k=>getJSON(env,k)))).filter(c=>c?.owner===id).map(c=>({nick:"참가자",messages:c.messages}));return response({memory:mem.memory,notes:notes.map(n=>({nick:n.nick||"",impression:n.impression,traits:n.traits,at:n.at})),chats});
 }
 if(path==="/api/admin"){
  if(req.method!=="POST")return fail(405,"POST만 가능해요.");const b=await jsonBody(req),r="class";
  if(b.action==="distribute"){const a=await assignLeftovers(env,r);if(a.error)return fail(400,a.error);await putJSON(env,`${base(r)}/meta.json`,{distributed:true,at:Date.now()});return response({ok:true,newlyAssigned:a.assigned,...await stats(env,r)});}
  if(b.action==="participants"){const names=await listKeys(env,`${base(r)}/mem/`);const people=(await Promise.all(names.map(async key=>{const m=await getJSON(env,key);if(!m)return null;const c=await getJSON(env,`${base(r)}/chat/${m.id}.json`);return{id:m.id,nick:m.nick||"익명",memory:m.memory,messages:c?.messages||[],at:m.at};}))).filter(Boolean).sort((a,b)=>a.at-b.at);return response({people});}
  if(b.action==="seed"){if(!env.LOCAL_TEST_MODE)return fail(403,"로컬 테스트에서만 사용할 수 있어요.");const styles=[["짧고 담백한 말투","결론을 먼저 말하고 군더더기를 줄인다","산책과 음악"],["밝고 장난스러운 말투","가벼운 농담으로 반응한다","영화와 간식"],["차분한 존댓말","상대의 말을 듣고 천천히 답한다","책과 글쓰기"],["호기심 많은 말투","왜 그런지 묻고 아이디어를 보탠다","과학과 만들기"],["활기찬 반말","감탄사를 자주 쓰고 빠르게 호응한다","운동과 야외 활동"],["꼼꼼한 말투","장단점을 나눠 생각한다","정리와 계획"],["부드러운 공감형 말투","상대의 감정을 먼저 받아 준다","그림과 전시"],["직설적인 말투","핵심을 분명하게 말한다","게임과 퍼즐"],["느긋한 말투","서두르지 않고 여유롭게 답한다","요리와 카페"],["재치 있는 말투","일상적인 비유를 섞는다","사진과 여행"]];let created=0;for(let i=0;i<styles.length;i++){const id=`local-demo-${String(i+1).padStart(2,"0")}`,key=`${base(r)}/mem/${id}.json`;if(await getJSON(env,key))continue;const [tone,reaction,interest]=styles[i];const memory=`# 사용자 메모리\n## 말투\n${tone}.\n## 자주 쓰는 표현\n- 그럴 수 있지\n- 한번 해보자\n- 괜찮네\n- 잠깐만\n- 좋아\n## 반응 패턴\n${reaction}.\n## 관심사와 가치관\n${interest}에 관심이 있다.\n## 실제 발화 예시\n- 오늘은 뭘 해볼까?\n- 그거 재미있겠다.\n- 음, 조금 생각해 볼게.\n## 재현 지침\n- ${tone}를 유지한다.\n- ${reaction}.\n- 민감한 개인정보를 만들지 않는다.`;await putJSON(env,key,{id,nick:`테스트 ${i+1}`,memory,at:Date.now()+i});created++;}return response({ok:true,created,...await stats(env,r)});}
  if(b.action==="purge"){const keys=await listKeys(env,`${base(r)}/`);for(let i=0;i<keys.length;i+=1000)await env.BUCKET.delete(keys.slice(i,i+1000));return response({ok:true,deleted:keys.length,...await stats(env,r)});}return response(await stats(env,r));
 }
 return fail(404,"요청한 API를 찾을 수 없어요.");
}
export default { async fetch(req,env){const url=new URL(req.url);if(url.pathname.startsWith("/api/"))return routeApi(req,env,url);if(url.pathname==="/"||url.pathname==="/index.html")return new Response(INDEX_HTML,{headers:{"content-type":"text/html; charset=utf-8"}});if(url.pathname==="/admin.html")return new Response(ADMIN_HTML,{headers:{"content-type":"text/html; charset=utf-8","x-robots-tag":"noindex"}});return new Response("Not found",{status:404});} };
