import React, { useState } from 'react';
import { HelpCircle } from 'lucide-react';

interface TechInfoTooltipProps {
  title: string;
  description: string;
  architectureDetails?: string;
  children?: React.ReactNode;
}

export const TechInfoTooltip: React.FC<TechInfoTooltipProps> = ({
  title,
  description,
  architectureDetails,
  children
}) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="relative inline-flex items-center group">
      {children}
      <button
        type="button"
        onMouseEnter={() => setIsOpen(true)}
        onMouseLeave={() => setIsOpen(false)}
        onClick={() => setIsOpen(!isOpen)}
        className="ml-1.5 p-0.5 rounded-full text-indigo-400 hover:text-indigo-300 hover:bg-indigo-950/40 transition-colors inline-flex items-center justify-center focus:outline-none"
        title={`Technical Info: ${title}`}
      >
        <HelpCircle className="w-3.5 h-3.5" />
      </button>

      {isOpen && (
        <div className="absolute z-50 bottom-full mb-2 left-1/2 -translate-x-1/2 w-80 p-3 bg-neutral-900 border border-neutral-700 rounded-xl shadow-2xl text-xs text-neutral-200 space-y-2 pointer-events-none animate-in fade-in zoom-in-95 duration-150">
          <div className="flex items-center justify-between border-b border-neutral-800 pb-1.5">
            <span className="font-bold text-amber-400 flex items-center gap-1">
              ⚡ {title}
            </span>
            <span className="text-[10px] font-mono text-neutral-400 bg-neutral-950 px-1.5 py-0.5 rounded border border-neutral-800">
              ABCI-MI Spec
            </span>
          </div>
          <p className="leading-relaxed text-neutral-300 text-[11.5px]">
            {description}
          </p>
          {architectureDetails && (
            <div className="bg-neutral-950 p-2 rounded border border-neutral-800 text-[11px] font-mono text-indigo-300 leading-normal">
              <span className="text-neutral-500 font-bold block mb-0.5">Architecture &amp; Algorithm:</span>
              {architectureDetails}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
