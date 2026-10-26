import { Suspense } from 'react';
import PlanningWorkspace from '@/components/owner/PlanningWorkspace';
import { OsLoading } from '@/components/os/States';
export default function PlanningPage(){return <Suspense fallback={<OsLoading/>}><PlanningWorkspace/></Suspense>;}
