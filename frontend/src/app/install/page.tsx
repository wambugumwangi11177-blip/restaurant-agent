"use client";
import { useEffect, useState } from 'react';
import Link from 'next/link';
type InstallPrompt=Event&{prompt:()=>Promise<void>;userChoice:Promise<{outcome:string}>};
export default function InstallPage(){
 const [prompt,setPrompt]=useState<InstallPrompt|null>(null),[message,setMessage]=useState('');
 useEffect(()=>{const available=(event:Event)=>{event.preventDefault();setPrompt(event as InstallPrompt);};const installed=()=>{setPrompt(null);setMessage('LEVIII is installed on this device.');};window.addEventListener('beforeinstallprompt',available);window.addEventListener('appinstalled',installed);return()=>{window.removeEventListener('beforeinstallprompt',available);window.removeEventListener('appinstalled',installed);};},[]);
 async function install(){if(!prompt)return;await prompt.prompt();const choice=await prompt.userChoice;setMessage(choice.outcome==='accepted'?'Follow your browser’s installation steps.':'You can install later from the browser menu.');setPrompt(null);}
 return <main className="min-h-screen bg-slate-950 p-6 text-slate-100"><div className="mx-auto max-w-2xl space-y-6"><Link className="inline-flex min-h-11 items-center underline" href="/login">← Sign in to LEVIII</Link><h1 className="text-3xl font-semibold">Install LEVIII</h1><p>Keep your restaurant workspace on your phone, tablet or desktop.</p>
 {prompt&&<button className="min-h-11 rounded-lg bg-amber-300 px-5 font-semibold text-black" onClick={install}>Install on this device</button>}{message&&<p role="status">{message}</p>}
 <section className="space-y-2 rounded-xl border border-slate-700 p-5"><h2 className="text-xl font-semibold">iPhone and iPad</h2><p>Open this website in Safari. Tap Share, then Add to Home Screen. Keep Open as Web App enabled if Safari offers it, then tap Add.</p><p>No App Store download is needed.</p></section>
 <section className="space-y-2 rounded-xl border border-slate-700 p-5"><h2 className="text-xl font-semibold">Android</h2><p>Open this website in Chrome. Use Install app or Add to Home screen in the menu. If your restaurant provides a signed Android package, install that release through its approved distribution channel.</p></section>
 <section className="space-y-2 rounded-xl border border-slate-700 p-5"><h2 className="text-xl font-semibold">Windows, macOS and Linux</h2><p>Use the install control in Chrome or Edge, or Add to Dock in supported Safari versions. Desktop installers are distributed separately after release testing.</p></section>
 <p className="text-sm text-slate-300">You need an internet connection to sign in and load screens. Only supported entry forms can queue work while offline; photos and reports need a connection. Installation does not give additional permissions.</p>
 </div></main>;
}
