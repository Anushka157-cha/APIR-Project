"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

export default function IncidentsPage() {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => {
    api("/incidents").then(setRows).catch(() => setRows([]));
  }, []);
  return (
    <div>
      <h1 className="text-2xl font-semibold">Incidents</h1>
      <table className="mt-4 w-full text-left text-sm">
        <thead className="text-neutral-500">
          <tr>
            <th className="py-2">Detected</th>
            <th>Title</th>
            <th>Severity</th>
            <th>Status</th>
            <th>Service</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((i) => (
            <tr key={i.incident_id} className="border-t border-line">
              <td className="py-2 font-mono text-xs">{i.detected_at}</td>
              <td>
                <Link className="text-accent" href={`/incidents/${i.incident_id}`}>
                  {i.title}
                </Link>
              </td>
              <td>{i.severity}</td>
              <td>{i.status}</td>
              <td>{i.service}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
