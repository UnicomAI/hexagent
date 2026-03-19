import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts";
import { Maximize2 } from "lucide-react";
import { useThemeMode } from "../hooks/useThemeMode";
import VizModal, { useVizModal } from "./VizModal";

export default function EChartsBlock({ children, actions }: { children: string; actions?: React.ReactNode }) {
  const chartRef = useRef<HTMLDivElement>(null);
  const modalChartRef = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<echarts.ECharts | null>(null);
  const modalInstanceRef = useRef<echarts.ECharts | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [parsedOption, setParsedOption] = useState<Record<string, unknown> | null>(null);
  const modal = useVizModal();
  const theme = useThemeMode();

  // Parse + render inline chart
  useEffect(() => {
    const el = chartRef.current;
    if (!el) return;

    try {
      const option = JSON.parse(children);
      setParsedOption(option);

      instanceRef.current?.dispose();
      instanceRef.current = echarts.init(el, theme === "dark" ? "dark" : undefined);
      instanceRef.current.setOption({ backgroundColor: "transparent", ...option }, true);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }

    return () => {
      instanceRef.current?.dispose();
      instanceRef.current = null;
    };
  }, [children, theme]);

  // Resize inline chart
  useEffect(() => {
    const el = chartRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => instanceRef.current?.resize());
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Render modal chart when expanded
  useEffect(() => {
    if (!modal.expanded || !parsedOption) return;

    const timer = setTimeout(() => {
      const el = modalChartRef.current;
      if (!el) return;

      modalInstanceRef.current?.dispose();
      modalInstanceRef.current = echarts.init(el, theme === "dark" ? "dark" : undefined);
      modalInstanceRef.current.setOption({ backgroundColor: "transparent", ...parsedOption }, true);
    }, 50);

    return () => {
      clearTimeout(timer);
      modalInstanceRef.current?.dispose();
      modalInstanceRef.current = null;
    };
  }, [modal.expanded, parsedOption, theme]);

  // Resize modal chart
  useEffect(() => {
    if (!modal.expanded) return;
    const el = modalChartRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => modalInstanceRef.current?.resize());
    observer.observe(el);
    return () => observer.disconnect();
  }, [modal.expanded]);

  if (error) {
    return <pre className="viz-error">{error}</pre>;
  }

  return (
    <>
      <div className="viz-container echarts-container">
        <div className="viz-actions-anchor">
          <div className="viz-actions">
            {actions}
            <button
              className="viz-action-btn"
              onClick={modal.open}
              aria-label="Expand chart"
            >
              <Maximize2 />
            </button>
          </div>
        </div>
        <div ref={chartRef} className="echarts-chart" />
      </div>

      <VizModal state={modal.state} onClose={modal.close} onExitDone={modal.onExitDone}>
        <div ref={modalChartRef} className="echarts-modal-chart" />
      </VizModal>
    </>
  );
}
