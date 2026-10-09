const EYE='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/></svg>';
const EYEOFF='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.9 17.9A10.9 10.9 0 0 1 12 19C5 19 1 12 1 12a18.5 18.5 0 0 1 5.1-5.9M9.9 5.1A10.7 10.7 0 0 1 12 5c7 0 11 7 11 7a18.6 18.6 0 0 1-2.2 3.2M1 1l22 22"/><path d="M14.1 14.1a3 3 0 1 1-4.2-4.2"/></svg>';
document.querySelectorAll('input[type=password]').forEach(inp=>{
  const w=document.createElement('div');w.className='pw';inp.parentNode.insertBefore(w,inp);w.appendChild(inp);
  const b=document.createElement('button');b.type='button';b.className='eye';b.innerHTML=EYE;b.setAttribute('aria-label','Show password');
  b.onclick=()=>{const s=inp.type==='password';inp.type=s?'text':'password';b.innerHTML=s?EYEOFF:EYE;b.setAttribute('aria-label',s?'Hide password':'Show password')};
  w.appendChild(b);
});
const hint=(el,msg)=>{let h=el.closest('.field').querySelector('.hint');h.textContent=msg||'';h.classList.toggle('show',!!msg);el.classList.toggle('invalid',!!msg);el.classList.toggle('valid',!msg&&el.value!=='')};
const checks={
 email:v=>!v?'Email is required.':!/^[^@\s]+@poornima\.edu\.in$/i.test(v.trim())?'Use your @poornima.edu.in email address.':'',
 password:v=>!v?'Password is required.':'',
 newpw:v=>!v?'Password is required.':v.length<8?'Password must be at least 8 characters.':v.length>72?'Password must be at most 72 characters.':!/[A-Za-z]/.test(v)?'Password must contain at least one letter.':!/\d/.test(v)?'Password must contain at least one number.':'',
 confirm:(v,f)=>!v?'Please confirm your password.':v!==f.querySelector('[data-v=newpw]').value?'Passwords do not match.':'',
 code:v=>!/^\d{6}$/.test(v.trim())?'Enter the 6-digit code.':'',
 file:v=>!v?'Please choose an .xlsx file.':!/\.xlsx$/i.test(v)?'Only .xlsx files are allowed.':''
};
document.querySelectorAll('form[data-validate]').forEach(f=>{
  const run=el=>{hint(el,checks[el.dataset.v](el.value,f));return !el.classList.contains('invalid')};
  f.querySelectorAll('[data-v]').forEach(el=>{el.addEventListener('blur',()=>run(el));el.addEventListener('input',()=>{if(el.classList.contains('invalid')||el.dataset.v==='newpw')run(el);
    if(el.dataset.v==='newpw'){const v=el.value;[['len',v.length>=8&&v.length<=72],['let',/[A-Za-z]/.test(v)],['num',/\d/.test(v)]].forEach(([k,ok])=>f.querySelector('[data-r='+k+']')?.classList.toggle('ok',ok))}})});
  f.addEventListener('submit',e=>{let ok=true;f.querySelectorAll('[data-v]').forEach(el=>{if(!run(el))ok=false});if(!ok)e.preventDefault()});
});
document.querySelectorAll('input[type=file]').forEach(i=>i.addEventListener('change',()=>{let n=i.closest('.drop').querySelector('.fname');if(!n){n=document.createElement('div');n.className='fname';i.closest('.drop').appendChild(n)}n.textContent=i.files[0]?'Selected: '+i.files[0].name:''}));
document.querySelectorAll('form[data-loading]').forEach(f=>f.addEventListener('submit',e=>{if(!e.defaultPrevented)document.getElementById('overlay')?.classList.add('show')}));