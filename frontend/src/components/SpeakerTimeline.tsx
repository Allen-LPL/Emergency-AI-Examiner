import React from 'react';
import { Tooltip } from 'antd';
import type { TranscriptSegment } from '../types';

interface SpeakerTimelineProps {
  transcription: TranscriptSegment[];
  duration: number;
}

const ROLE_NAMES: Record<string, string> = {
  doctor: '医生',
  nurse: '护士',
  driver: '驾驶员',
  unknown: '未知',
};

const ROLE_COLORS: Record<string, string> = {
  doctor: '#1677ff',
  nurse: '#52c41a',
  driver: '#fa8c16',
  unknown: '#d9d9d9',
};

const ROLES = ['doctor', 'nurse', 'driver'];

export const SpeakerTimeline: React.FC<SpeakerTimelineProps> = ({ transcription, duration }) => {
  const safeDuration = Math.max(duration, 1);

  return (
    <div className="w-full bg-white p-4 rounded-lg border border-gray-200 shadow-sm">
      <div className="flex flex-col gap-4">
        {ROLES.map((role) => {
          const segments = transcription.filter(
            (seg) => seg.speaker_role === role || (role === 'unknown' && !seg.speaker_role)
          );

          return (
            <div key={role} className="flex items-center h-8">
              <div className="w-20 text-sm font-medium text-gray-600 shrink-0">
                {ROLE_NAMES[role]}
              </div>
              <div className="flex-1 h-full bg-gray-50 rounded relative overflow-hidden border border-gray-100">
                {segments.map((seg, idx) => {
                  const left = (seg.start / safeDuration) * 100;
                  const width = ((seg.end - seg.start) / safeDuration) * 100;
                  
                  return (
                    <Tooltip 
                      key={idx} 
                      title={
                        <div className="text-xs">
                          <div className="font-semibold mb-1">
                            {seg.start.toFixed(1)}s - {seg.end.toFixed(1)}s
                          </div>
                          <div>{seg.text}</div>
                        </div>
                      }
                    >
                      <div
                        className="absolute h-full rounded-sm cursor-pointer transition-opacity hover:opacity-80"
                        style={{
                          left: `${Math.max(0, Math.min(100, left))}%`,
                          width: `${Math.max(0.5, Math.min(100 - left, width))}%`,
                          backgroundColor: ROLE_COLORS[role],
                        }}
                      />
                    </Tooltip>
                  );
                })}
              </div>
            </div>
          );
        })}
        
        <div className="flex items-center h-6 mt-2">
          <div className="w-20 shrink-0" />
          <div className="flex-1 relative h-full border-t border-gray-300">
            {[0, 0.25, 0.5, 0.75, 1].map((tick) => (
              <div
                key={tick}
                className="absolute top-0 -translate-x-1/2 flex flex-col items-center"
                style={{ left: `${tick * 100}%` }}
              >
                <div className="w-px h-2 bg-gray-300" />
                <div className="text-xs text-gray-400 mt-1">
                  {(tick * safeDuration).toFixed(0)}s
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
