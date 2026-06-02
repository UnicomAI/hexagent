/**
 * Excel spreadsheet viewer built on SheetJS (xlsx).
 *
 * Lazy-loaded via React.lazy() — SheetJS is only fetched
 * when a user actually opens an .xlsx file.
 *
 * Layout mirrors Microsoft Excel:
 *   - Column letters (A, B, C, …, AA, …) across the top
 *   - Row numbers (1, 2, 3, …) down the left
 *   - Gray header cells, white data cells, thin grid lines
 *   - Sheet tabs at the bottom when multiple sheets exist
 */

import { useState, useEffect, useMemo, useCallback } from "react";
import * as XLSX from "xlsx";
import { Loader2 } from "lucide-react";

const MAX_ROWS = 500;

/** Convert 0-based column index to Excel column letter (0→A, 25→Z, 26→AA). */
function colLetter(index: number): string {
  let s = "";
  let n = index;
  while (n >= 0) {
    s = String.fromCharCode(65 + (n % 26)) + s;
    n = Math.floor(n / 26) - 1;
  }
  return s;
}

interface Props {
  url: string;
}

function XlsxViewer({ url }: Props) {
  const [workbook, setWorkbook] = useState<XLSX.WorkBook | null>(null);
  const [activeSheet, setActiveSheet] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);
    setWorkbook(null);

    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch");
        return res.arrayBuffer();
      })
      .then((buffer) => {
        if (cancelled) return;
        const wb = XLSX.read(new Uint8Array(buffer), { type: "array" });
        setWorkbook(wb);
        setActiveSheet(wb.SheetNames[0] || "");
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) {
          setError(true);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [url]);

  const { colCount, rows, totalRows } = useMemo(() => {
    if (!workbook || !activeSheet)
      return { colCount: 0, rows: [], totalRows: 0 };
    const ws = workbook.Sheets[activeSheet];
    if (!ws) return { colCount: 0, rows: [], totalRows: 0 };

    const data = XLSX.utils.sheet_to_json<string[]>(ws, {
      header: 1,
      defval: "",
    });
    if (data.length === 0) return { colCount: 0, rows: [], totalRows: 0 };

    // Max column count across all rows
    const maxCols = data.reduce((max, row) => Math.max(max, row.length), 0);

    // Normalize every row to the same column count
    const allRows = data.map((row) => {
      const r = row.map((v) => String(v));
      while (r.length < maxCols) r.push("");
      return r;
    });

    return {
      colCount: maxCols,
      rows: allRows.slice(0, MAX_ROWS),
      totalRows: allRows.length,
    };
  }, [workbook, activeSheet]);

  const handleTabClick = useCallback((name: string) => {
    setActiveSheet(name);
  }, []);

  if (loading) {
    return (
      <div className="file-preview-loading">
        <Loader2 size={24} className="file-preview-spinner" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="file-preview-unsupported">
        <p>Failed to load spreadsheet.</p>
      </div>
    );
  }

  if (!workbook) return null;

  const sheetNames = workbook.SheetNames;
  const capped = totalRows > MAX_ROWS;

  return (
    <div className="xlsx-viewer">
      <div className="xlsx-viewer-table-wrapper">
        {colCount === 0 ? (
          <div className="file-preview-unsupported">
            <p>This sheet is empty.</p>
          </div>
        ) : (
          <table className="xlsx-viewer-table">
            <thead>
              <tr>
                <th className="xlsx-viewer-corner" />
                {Array.from({ length: colCount }, (_, i) => (
                  <th key={i}>{colLetter(i)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, ri) => (
                <tr key={ri}>
                  <td className="xlsx-viewer-row-num">{ri + 1}</td>
                  {row.map((cell, ci) => (
                    <td key={ci}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {capped && (
          <div className="xlsx-viewer-cap-notice">
            Showing {MAX_ROWS} of {totalRows.toLocaleString()} rows. Download to
            see all data.
          </div>
        )}
      </div>
      <div className="xlsx-viewer-tabs">
        {sheetNames.map((name) => (
          <button
            key={name}
            className={`xlsx-viewer-tab${name === activeSheet ? " xlsx-viewer-tab--active" : ""}`}
            onClick={() => handleTabClick(name)}
          >
            {name}
          </button>
        ))}
      </div>
    </div>
  );
}

export default XlsxViewer;
