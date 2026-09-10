import React, { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import { Activity, Volume2, ShieldCheck, Wifi } from 'lucide-react';

interface ConfidencePoint {
  sequence: number;
  confidence: number;
  speaker: string;
}

interface D3LiveTelemetryChartsProps {
  volumeData: number[];
  confidenceData: ConfidencePoint[];
  latencyData: number[];
  isLive: boolean;
}

export const D3LiveTelemetryCharts: React.FC<D3LiveTelemetryChartsProps> = ({
  volumeData,
  confidenceData,
  latencyData,
  isLive,
}) => {
  const volumeSvgRef = useRef<SVGSVGElement | null>(null);
  const confidenceSvgRef = useRef<SVGSVGElement | null>(null);
  const latencySvgRef = useRef<SVGSVGElement | null>(null);

  // 1. Audio Volume D3 Chart
  useEffect(() => {
    if (!volumeSvgRef.current) return;
    const svg = d3.select(volumeSvgRef.current);
    svg.selectAll('*').remove();

    const width = 320;
    const height = 120;
    const margin = { top: 10, right: 10, bottom: 20, innerWidth: 30 };

    const chartWidth = width - margin.innerWidth - margin.right;
    const chartHeight = height - margin.top - margin.bottom;

    const g = svg
      .attr('viewBox', `0 0 ${width} ${height}`)
      .append('g')
      .attr('transform', `translate(${margin.innerWidth}, ${margin.top})`);

    const data = volumeData.length > 0 ? volumeData : [20, 45, 30, 60, 80, 50, 40, 65, 75, 45];

    const xScale = d3
      .scaleLinear()
      .domain([0, data.length - 1])
      .range([0, chartWidth]);

    const yScale = d3
      .scaleLinear()
      .domain([0, 100])
      .range([chartHeight, 0]);

    // Area generator
    const area = d3
      .area<number>()
      .x((d, i) => xScale(i))
      .y0(chartHeight)
      .y1(d => yScale(d))
      .curve(d3.curveMonotoneX);

    // Line generator
    const line = d3
      .line<number>()
      .x((d, i) => xScale(i))
      .y(d => yScale(d))
      .curve(d3.curveMonotoneX);

    // Gradient fill
    const defs = svg.append('defs');
    const gradient = defs
      .append('linearGradient')
      .attr('id', 'volume-gradient')
      .attr('x1', '0%')
      .attr('y1', '0%')
      .attr('x2', '0%')
      .attr('y2', '100%');

    gradient.append('stop').attr('offset', '0%').attr('stop-color', '#818cf8').attr('stop-opacity', 0.6);
    gradient.append('stop').attr('offset', '100%').attr('stop-color', '#818cf8').attr('stop-opacity', 0.0);

    // Axes
    g.append('g')
      .attr('transform', `translate(0, ${chartHeight})`)
      .call(d3.axisBottom(xScale).ticks(5).tickSize(0))
      .selectAll('text')
      .style('fill', '#737373')
      .style('font-size', '9px');

    g.append('g')
      .call(d3.axisLeft(yScale).ticks(3).tickSize(0))
      .selectAll('text')
      .style('fill', '#737373')
      .style('font-size', '9px');

    // Remove domain lines for clean look
    g.selectAll('.domain').remove();

    // Append Area
    g.append('path')
      .datum(data)
      .attr('fill', 'url(#volume-gradient)')
      .attr('d', area);

    // Append Line
    g.append('path')
      .datum(data)
      .attr('fill', 'none')
      .attr('stroke', '#6366f1')
      .attr('stroke-width', 2)
      .attr('d', line);

  }, [volumeData]);

  // 2. Transcript Confidence D3 Bar / Scatter Chart
  useEffect(() => {
    if (!confidenceSvgRef.current) return;
    const svg = d3.select(confidenceSvgRef.current);
    svg.selectAll('*').remove();

    const width = 320;
    const height = 120;
    const margin = { top: 10, right: 10, bottom: 20, innerWidth: 30 };

    const chartWidth = width - margin.innerWidth - margin.right;
    const chartHeight = height - margin.top - margin.bottom;

    const g = svg
      .attr('viewBox', `0 0 ${width} ${height}`)
      .append('g')
      .attr('transform', `translate(${margin.innerWidth}, ${margin.top})`);

    const data: ConfidencePoint[] =
      confidenceData.length > 0
        ? confidenceData
        : [
            { sequence: 1, confidence: 0.94, speaker: 'Speaker 0' },
            { sequence: 2, confidence: 0.91, speaker: 'Speaker 1' },
            { sequence: 3, confidence: 0.97, speaker: 'Speaker 0' },
            { sequence: 4, confidence: 0.89, speaker: 'Speaker 1' },
            { sequence: 5, confidence: 0.95, speaker: 'Speaker 0' },
          ];

    const xScale = d3
      .scaleBand<string>()
      .domain(data.map((d: ConfidencePoint) => d.sequence.toString()))
      .range([0, chartWidth])
      .padding(0.3);

    const yScale = d3
      .scaleLinear()
      .domain([0.7, 1.0])
      .range([chartHeight, 0]);

    // Axes
    g.append('g')
      .attr('transform', `translate(0, ${chartHeight})`)
      .call(d3.axisBottom(xScale).tickSize(0))
      .selectAll('text')
      .style('fill', '#737373')
      .style('font-size', '9px');

    g.append('g')
      .call(d3.axisLeft(yScale).ticks(3).tickSize(0))
      .selectAll('text')
      .style('fill', '#737373')
      .style('font-size', '9px');

    g.selectAll('.domain').remove();

    // Bars
    g.selectAll('.confidence-bar')
      .data(data)
      .enter()
      .append('rect')
      .attr('class', 'confidence-bar')
      .attr('x', (d: ConfidencePoint) => xScale(d.sequence.toString()) || 0)
      .attr('y', (d: ConfidencePoint) => yScale(d.confidence))
      .attr('width', xScale.bandwidth())
      .attr('height', (d: ConfidencePoint) => chartHeight - yScale(d.confidence))
      .attr('fill', '#34d399')
      .attr('rx', 3);

  }, [confidenceData]);

  // 3. Connection Latency D3 Line Chart
  useEffect(() => {
    if (!latencySvgRef.current) return;
    const svg = d3.select(latencySvgRef.current);
    svg.selectAll('*').remove();

    const width = 320;
    const height = 120;
    const margin = { top: 10, right: 10, bottom: 20, innerWidth: 30 };

    const chartWidth = width - margin.innerWidth - margin.right;
    const chartHeight = height - margin.top - margin.bottom;

    const g = svg
      .attr('viewBox', `0 0 ${width} ${height}`)
      .append('g')
      .attr('transform', `translate(${margin.innerWidth}, ${margin.top})`);

    const data = latencyData.length > 0 ? latencyData : [24, 28, 32, 26, 29, 25, 30, 27, 28, 26];

    const xScale = d3
      .scaleLinear()
      .domain([0, data.length - 1])
      .range([0, chartWidth]);

    const yScale = d3
      .scaleLinear()
      .domain([10, 60])
      .range([chartHeight, 0]);

    const line = d3
      .line<number>()
      .x((d, i) => xScale(i))
      .y(d => yScale(d))
      .curve(d3.curveMonotoneX);

    g.append('g')
      .attr('transform', `translate(0, ${chartHeight})`)
      .call(d3.axisBottom(xScale).ticks(5).tickSize(0))
      .selectAll('text')
      .style('fill', '#737373')
      .style('font-size', '9px');

    g.append('g')
      .call(d3.axisLeft(yScale).ticks(3).tickSize(0))
      .selectAll('text')
      .style('fill', '#737373')
      .style('font-size', '9px');

    g.selectAll('.domain').remove();

    g.append('path')
      .datum(data)
      .attr('fill', 'none')
      .attr('stroke', '#a78bfa')
      .attr('stroke-width', 2)
      .attr('d', line);

    // Data points
    g.selectAll('.dot')
      .data(data)
      .enter()
      .append('circle')
      .attr('cx', (d: number, i: number) => xScale(i))
      .attr('cy', (d: number) => yScale(d))
      .attr('r', 3)
      .attr('fill', '#c084fc');

  }, [latencyData]);

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {/* Chart 1: Audio Volume */}
      <div className="bg-neutral-950 p-4 rounded-xl border border-neutral-800 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold text-white flex items-center gap-1.5">
            <Volume2 className="w-3.5 h-3.5 text-indigo-400" />
            Audio Waveform RMS
          </span>
          <span className="text-[10px] font-mono text-indigo-400 bg-indigo-950/40 px-2 py-0.5 rounded">
            {isLive ? 'Live Stream' : 'Idle'}
          </span>
        </div>
        <div className="w-full">
          <svg ref={volumeSvgRef} className="w-full h-28" />
        </div>
      </div>

      {/* Chart 2: Transcript Confidence */}
      <div className="bg-neutral-950 p-4 rounded-xl border border-neutral-800 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold text-white flex items-center gap-1.5">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            Transcript Confidence
          </span>
          <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950/40 px-2 py-0.5 rounded">
            ASR Model
          </span>
        </div>
        <div className="w-full">
          <svg ref={confidenceSvgRef} className="w-full h-28" />
        </div>
      </div>

      {/* Chart 3: Connection Latency */}
      <div className="bg-neutral-950 p-4 rounded-xl border border-neutral-800 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold text-white flex items-center gap-1.5">
            <Wifi className="w-3.5 h-3.5 text-purple-400" />
            Connection Latency (RTT)
          </span>
          <span className="text-[10px] font-mono text-purple-400 bg-purple-950/40 px-2 py-0.5 rounded">
            WebSocket / WebRTC
          </span>
        </div>
        <div className="w-full">
          <svg ref={latencySvgRef} className="w-full h-28" />
        </div>
      </div>
    </div>
  );
};
