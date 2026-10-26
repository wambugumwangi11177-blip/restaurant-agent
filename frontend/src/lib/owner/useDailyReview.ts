"use client";
import {useEffect,useState} from 'react';
export const dailyReviewDate=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Africa/Nairobi',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
/** Refresh read-only projections at a new Nairobi day, including a sleeping tab. */
export function useDailyReview(){
 const [day,setDay]=useState(dailyReviewDate);
 useEffect(()=>{const check=()=>setDay(dailyReviewDate());const timer=setInterval(check,60000);window.addEventListener('focus',check);document.addEventListener('visibilitychange',check);return()=>{clearInterval(timer);window.removeEventListener('focus',check);document.removeEventListener('visibilitychange',check);};},[]);
 return day;
}
