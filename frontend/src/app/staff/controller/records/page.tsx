import {Suspense} from 'react';
import DailyStockWorkspace from '@/components/operations/DailyStockWorkspace';
export default function StockRecords(){return <Suspense fallback={<p>Loading stock records…</p>}><DailyStockWorkspace/></Suspense>;}
