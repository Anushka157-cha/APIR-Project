"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
export default function FailureInjectionPage() {
 const [data,setData]=useState<any>({scenarios:{},active:[]}); const [error,setError]=useState(""); const load=()=>api("/failures").then(setData).catch(e=>setError(String(e))); useEffect(()=>{load()},[]);
 const active=new Set((data.active||[]).map((x:any)=>x.scenario)); const run=(name:string,start:boolean)=>{if(start&&!confirm(`Start ${name}? This intentionally disrupts a service.`))return; api(`/failures/${name}/${start?"start":"stop"}`,{method:"POST"}).then(load).catch(e=>setError(String(e)))};
 return <div><h1 className="text-2xl font-semibold">Failure injection</h1><p className="mt-1 text-sm text-neutral-400">SRE/Admin controls are enforced by the API.</p>{error&&<p className="mt-3 text-bad">{error}</p>}<div className="mt-6 space-y-3">{Object.entries(data.scenarios||{}).map(([name,s]:any)=><div className="rounded border border-line bg-card p-4" key={name}><div className="flex items-center justify-between"><div><div className="font-mono">{name}</div><div className="text-sm text-neutral-400">{s.description} · {s.target} · {s.severity}</div></div>{active.has(name)?<button className="text-bad" onClick={()=>run(name,false)}>Stop</button>:<button className="text-accent" onClick={()=>run(name,true)}>Start</button>}</div></div>)}</div></div>;
}
