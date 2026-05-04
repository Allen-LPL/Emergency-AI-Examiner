import React from 'react';
import { Table, Progress, Tag } from 'antd';
import { CheckCircleOutlined, WarningOutlined } from '@ant-design/icons';
import type { VoiceMatch } from '../types';

interface TemplateMatchViewProps {
  matches: VoiceMatch[];
}

const ROLE_NAMES: Record<string, string> = {
  doctor: '医生',
  nurse: '护士',
  driver: '驾驶员',
  unknown: '未知',
};

const ROLE_COLORS: Record<string, string> = {
  doctor: 'blue',
  nurse: 'green',
  driver: 'orange',
  unknown: 'default',
};

const PHASE_NAMES: Record<string, string> = {
  phase1_before_arrival: '到达现场前',
  phase2_arrival_step1: '到达现场(一)',
  phase3_arrival_step2: '到达现场(二)',
  phase4_arrival_step3: '到达现场(三)',
  phase5_arrival_step4: '到达现场(四)',
  phase6_arrival_step5: '到达现场(五)',
  objective_compression: '客观评分-按压',
  objective_ventilation: '客观评分-通气',
  objective_ccf: '客观评分-CCF',
};

export const TemplateMatchView: React.FC<TemplateMatchViewProps> = ({ matches }) => {
  const columns = [
    {
      title: '时间(s)',
      dataIndex: 'time',
      key: 'time',
      sorter: (a: VoiceMatch, b: VoiceMatch) => a.time - b.time,
      render: (time: number) => `${time.toFixed(1)}s`,
      width: 100,
    },
    {
      title: '阶段',
      dataIndex: 'phase',
      key: 'phase',
      render: (phase: string) => PHASE_NAMES[phase] || phase,
      width: 120,
    },
    {
      title: '规则名',
      dataIndex: 'rule_name',
      key: 'rule_name',
      width: 150,
    },
    {
      title: '匹配度',
      dataIndex: 'similarity',
      key: 'similarity',
      sorter: (a: VoiceMatch, b: VoiceMatch) => a.similarity - b.similarity,
      render: (similarity: number) => {
        const percent = Math.round(similarity * 100);
        let strokeColor = '#f5222d';
        if (percent >= 80) strokeColor = '#52c41a';
        else if (percent >= 60) strokeColor = '#fa8c16';

        return (
          <Progress 
            percent={percent} 
            size="small" 
            strokeColor={strokeColor} 
            format={(p) => `${p}%`}
          />
        );
      },
      width: 150,
    },
    {
      title: '说话人',
      dataIndex: 'speaker',
      key: 'speaker',
      width: 100,
    },
    {
      title: '角色',
      key: 'role',
      render: (_: unknown, record: VoiceMatch) => {
        const role = record.speaker_role || 'unknown';
        return (
          <div className="flex items-center gap-2">
            <Tag color={ROLE_COLORS[role]}>{ROLE_NAMES[role] || role}</Tag>
            {record.role_correct ? (
              <CheckCircleOutlined className="text-green-500" />
            ) : (
              <WarningOutlined className="text-orange-500" title="角色不匹配" />
            )}
          </div>
        );
      },
      width: 120,
    },
    {
      title: '匹配内容',
      dataIndex: 'matched_text',
      key: 'matched_text',
      ellipsis: true,
    },
    {
      title: '模板',
      dataIndex: 'matched_template',
      key: 'matched_template',
      ellipsis: true,
    },
  ];

  return (
    <div className="bg-white p-4 rounded-lg border border-gray-200 shadow-sm">
      <Table
        dataSource={matches}
        columns={columns}
        rowKey={(record) => `${record.time}-${record.rule_code}`}
        pagination={{ pageSize: 10 }}
        size="small"
      />
    </div>
  );
};
