'use client';

import { useEffect, useState } from 'react';
import type { ZiweiChart } from '@/lib/ziwei/types';

const TOPICS: [string, string][] = [
  ['overview','命格总览'], ['personality','性格'], ['love','感情婚姻'],
  ['career','事业'], ['wealth','财运'], ['health','健康'],
  ['family','兄弟合伙'], ['children','子女'], ['move','迁移'],
  ['friends','人际贵人'], ['home','田宅'], ['spirit','精神福德'],
  ['parents','父母长辈'],
];

type DatasetRecord = {
  k: string;
  c: Record<string, string>;
};

/** The only network lookup is /interpretations/YEAR.jsonl.gz.
 * Date, time, gender, name and chart are never placed in the request.
 */
export default function PrivateInterpretation({ chart }: { chart: ZiweiChart }) {
  const [readings, setReadings] = useState<Record<string,string> | null>(null);
  const [selected, setSelected] = useState('overview');
  const [status, setStatus] = useState('准备读取解读数据…');

  useEffect(() => {
    const { year, month, day, hour, gender } = chart.birthInfo;
    const ac = new AbortController();
    const key = `${year}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}-${hour}-${gender}`;
    setReadings(null);
    setSelected('overview');
    setStatus('正在读取该年份的公开解读数据（不上传个人出生信息）…');

    async function load() {
      if (year < 1950 || year > 2026) {
        setStatus('v4 数据集仅覆盖 1950–2026 年。');
        return;
      }
      try {
        const res = await fetch(`/interpretations/${year}.jsonl.gz`, {
          signal: ac.signal,
          cache: 'force-cache',
        });
        if (res.status === 404) {
          setStatus(`${year} 年数据尚未准备。请在 GitHub Actions 运行“Prepare v4 interpretations for one year”，输入 ${year} 后等待 Vercel 重新部署。`);
          return;
        }
        if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
        if (typeof DecompressionStream === 'undefined') {
          throw new Error('浏览器不支持 DecompressionStream，请尝试最新版 Chrome / Edge。');
        }

        // One record per line; never keep the full ~700MB decompressed year in memory.
        const textStream = res.body.pipeThrough(new DecompressionStream('gzip')).pipeThrough(new TextDecoderStream());
        const reader = textStream.getReader();
        let buf = '';
        let found: DatasetRecord | null = null;
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += value;
            let end;
            while ((end = buf.indexOf('\n')) >= 0) {
              const line = buf.slice(0,end);
              buf = buf.slice(end+1);
              if (!line) continue;
              // Avoid parsing all records: the stable key is the first field in upstream JSON.
              if (!line.includes(`"k":"${key}"`) && !line.includes(`"k": "${key}"`)) continue;
              const record = JSON.parse(line) as DatasetRecord;
              if (record.k === key && record.c) { found = record; break; }
            }
            if (found) break;
          }
        } finally {
          // Stop streaming once the desired chart was found.
          await reader.cancel().catch(() => undefined);
        }
        if (ac.signal.aborted) return;
        if (!found) {
          setStatus('未在该年份数据中找到匹配记录。请检查公历出生日期、时辰及性别。');
          return;
        }
        setReadings(found.c);
        setStatus('');
      } catch(e) {
        if (ac.signal.aborted) return;
        setStatus(e instanceof Error ? `读取失败：${e.message}` : '读取失败');
      }
    }
    void load();
    return () => ac.abort();
  }, [chart]);

  return (
    <section className="rounded-xl border p-4 mt-4" style={{ borderColor: 'var(--t-border)' }}>
      <h2 className="text-lg font-semibold mb-2">紫微斗数 · 13维传统解读</h2>
      <p className="text-xs opacity-70 mb-3">数据来源：Renhuai123/ziwei-doushu v4.0。解读为传统文化参考，并非科学预测或医疗、财务建议。</p>
      {status && <p role="status" className="text-sm mb-3">{status}</p>}
      {readings && (
        <>
          <div className="flex flex-wrap gap-2 mb-4">
            {TOPICS.map(([id,label]) => (
              <button key={id} type="button" onClick={() => setSelected(id)}
                className="rounded-lg border px-3 py-2 text-sm"
                style={{ borderColor: selected === id ? 'var(--t-gold)' : 'var(--t-border)',
                  color: selected === id ? 'var(--t-gold)' : 'var(--t-text)' }}>
                {label}
              </button>
            ))}
          </div>
          <div className="whitespace-pre-wrap leading-7 text-sm break-words" style={{ color: 'var(--t-text)' }}>
            {readings[selected] || '该维度没有可用内容。'}
          </div>
        </>
      )}
      <p className="text-xs opacity-60 mt-4">
        来源：<a href="https://github.com/Renhuai123/ziwei-doushu" target="_blank" rel="noreferrer" className="underline">紫微斗数开源解读数据集 v4.0</a> · 原作者：王多鱼AI
      </p>
    </section>
  );
}
