import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Spin, Result, Collapse, Table, Tag, Card, message } from 'antd';
import { ArrowLeftOutlined, VideoCameraOutlined, CheckCircleOutlined, CloseCircleOutlined, WarningOutlined, FilePdfOutlined } from '@ant-design/icons';
import { downloadExamReportPdf, getExamResult } from '../api';
import type { ScoreResult } from '../types';
import RadarChart from '../components/RadarChart';

const { Panel } = Collapse;

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

const Report: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const examId = parseInt(id || '0', 10);
  
  const [result, setResult] = useState<ScoreResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);

  const handleDownloadPdf = async () => {
    if (!examId) return;
    setDownloading(true);
    try {
      await downloadExamReportPdf(examId);
      message.success('PDF 报告已开始下载');
    } catch (error) {
      console.error('下载 PDF 失败:', error);
      message.error('下载 PDF 失败，请稍后重试');
    } finally {
      setDownloading(false);
    }
  };

  useEffect(() => {
    const fetchResult = async () => {
      if (!examId) return;
      try {
        const data = await getExamResult(examId);
        setResult(data);
      } catch (error) {
        console.error('Failed to fetch exam result:', error);
      } finally {
        setLoading(false);
      }
    };
    
    fetchResult();
  }, [examId]);

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <Spin size="large" tip="生成报告中..." />
      </div>
    );
  }

  if (!result) {
    return <Result status="404" title="未找到考核报告" />;
  }

  const getEvidenceTags = (item: any) => {
    const tags = [];
    if (item.rule_code.includes('voice') || item.rule_name.includes('告知') || item.rule_name.includes('呼叫')) {
      tags.push(<Tag key="audio" color="blue" className="text-xs m-0">音频</Tag>);
    } else if (item.rule_code.includes('sensor') || item.phase.includes('objective')) {
      tags.push(<Tag key="sensor" color="orange" className="text-xs m-0">传感器</Tag>);
    } else if (item.actual_score === item.max_score && !item.deduction_reason) {
      tags.push(<Tag key="default" color="default" className="text-xs m-0">默认</Tag>);
    } else {
      tags.push(<Tag key="video" color="green" className="text-xs m-0">视频</Tag>);
    }
    return tags;
  };

  const columns = [
    {
      title: '评分项',
      dataIndex: 'rule_name',
      key: 'rule_name',
      width: '35%',
      render: (text: string, record: any) => (
        <div className="flex items-center gap-2">
          {record.actual_score === record.max_score ? (
            <CheckCircleOutlined className="text-green-500" />
          ) : (
            <CloseCircleOutlined className="text-red-500" />
          )}
          <span className="font-medium text-gray-800">{text}</span>
        </div>
      ),
    },
    {
      title: '得分',
      key: 'score',
      width: '15%',
      render: (_: any, record: any) => {
        const isFull = record.actual_score === record.max_score;
        const isZero = record.actual_score === 0;
        return (
          <Tag color={isFull ? 'success' : isZero ? 'error' : 'warning'} className="text-sm px-3 py-1">
            {record.actual_score} / {record.max_score}
          </Tag>
        );
      },
    },
    {
      title: '证据来源',
      key: 'evidence',
      width: '15%',
      render: (_: any, record: any) => (
        <div className="flex gap-1 flex-wrap">
          {getEvidenceTags(record)}
        </div>
      ),
    },
    {
      title: '扣分原因',
      dataIndex: 'deduction_reason',
      key: 'deduction_reason',
      render: (text: string | null) => text ? <span className="text-red-500">{text}</span> : <span className="text-gray-400">-</span>,
    },
  ];

  const groupedItems = result.items.reduce((acc, item) => {
    if (!acc[item.phase]) {
      acc[item.phase] = [];
    }
    acc[item.phase].push(item);
    return acc;
  }, {} as Record<string, typeof result.items>);

  const deductions = result.items.filter(item => item.actual_score < item.max_score);
  const scoreColor = result.total_score < 40 ? 'text-red-500' : result.total_score < 70 ? 'text-orange-500' : 'text-green-500';

  return (
    <div className="space-y-8 pb-12 max-w-6xl mx-auto">
      <div className="flex justify-between items-center bg-white p-4 rounded-lg shadow-sm border border-gray-200">
        <div className="flex items-center gap-4">
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(`/exam/${examId}`)}>返回详情</Button>
          <h2 className="text-2xl font-bold m-0 text-gray-800">考核分析报告</h2>
        </div>
        <div className="flex items-center gap-3">
          <Button
            icon={<FilePdfOutlined />}
            onClick={handleDownloadPdf}
            loading={downloading}
          >
            下载 PDF
          </Button>
          <Button type="primary" icon={<VideoCameraOutlined />} onClick={() => navigate('/')}>
            返回首页
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-1 shadow-sm border-gray-200 flex flex-col justify-center items-center py-8">
          <div className="text-gray-500 text-lg mb-2">最终得分</div>
          <div className={`text-7xl font-bold ${scoreColor} mb-4`}>
            {result.total_score.toFixed(1)}
          </div>
          <div className="text-gray-400 text-xl">/ {result.max_total}</div>
          
          <div className="mt-8 w-full px-8">
            <div className="flex justify-between text-sm text-gray-500 mb-2">
              <span>通过率</span>
              <span>{((result.items.filter(i => i.actual_score === i.max_score).length / result.items.length) * 100).toFixed(0)}%</span>
            </div>
            <div className="w-full bg-gray-100 rounded-full h-2">
              <div 
                className="bg-blue-500 h-2 rounded-full" 
                style={{ width: `${(result.items.filter(i => i.actual_score === i.max_score).length / result.items.length) * 100}%` }}
              ></div>
            </div>
          </div>
        </Card>
        
        <Card className="lg:col-span-2 shadow-sm border-gray-200">
          <RadarChart phaseScores={result.phase_scores} />
        </Card>
      </div>

      {deductions.length > 0 && (
        <div className="bg-red-50 p-6 rounded-lg border border-red-100 shadow-sm">
          <h3 className="text-lg font-bold text-red-800 mb-4 flex items-center gap-2">
            <WarningOutlined /> 主要扣分项汇总
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {deductions.map((item, idx) => (
              <div key={idx} className="bg-white p-4 rounded border border-red-100 flex flex-col gap-2">
                <div className="flex justify-between items-start">
                  <span className="font-medium text-gray-800">{item.rule_name}</span>
                  <Tag color="error" className="m-0">-{item.max_score - item.actual_score}分</Tag>
                </div>
                <div className="text-sm text-gray-500">[{PHASE_NAMES[item.phase] || item.phase}]</div>
                <div className="text-red-600 text-sm mt-1 bg-red-50 p-2 rounded">{item.deduction_reason}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h3 className="text-xl font-bold text-gray-800 mb-6">详细评分明细</h3>
        <Collapse 
          defaultActiveKey={Object.keys(groupedItems)} 
          ghost 
          className="bg-transparent"
          expandIconPosition="end"
        >
          {Object.entries(groupedItems).map(([phase, items]) => {
            const phaseScore = result.phase_scores[phase];
            const isFullScore = phaseScore.score === phaseScore.max_score;
            
            const header = (
              <div className="flex justify-between items-center w-full pr-8 py-2">
                <span className="text-lg font-bold text-gray-800">{PHASE_NAMES[phase] || phase}</span>
                <div className="flex items-center gap-3">
                  <span className="text-gray-500">得分:</span>
                  <span className={`text-xl font-bold ${isFullScore ? 'text-green-600' : 'text-orange-500'}`}>
                    {phaseScore.score}
                  </span>
                  <span className="text-gray-400">/ {phaseScore.max_score}</span>
                </div>
              </div>
            );
            
            return (
              <Panel 
                header={header} 
                key={phase}
                className="border-b border-gray-100 last:border-0 mb-4 bg-gray-50 rounded-lg overflow-hidden"
              >
                <Table 
                  columns={columns} 
                  dataSource={items} 
                  rowKey="rule_code" 
                  pagination={false}
                  size="middle"
                  className="bg-white"
                />
              </Panel>
            );
          })}
        </Collapse>
      </div>
    </div>
  );
};

export default Report;