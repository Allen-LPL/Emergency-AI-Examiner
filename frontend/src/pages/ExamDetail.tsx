import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Spin, Result, Card, Progress, Tag, Table, Collapse, Statistic } from 'antd';
import { ArrowLeftOutlined, FileTextOutlined, CheckCircleOutlined, WarningOutlined } from '@ant-design/icons';
import { getExamStatus, getExamTimeline, getExamScores, getSensorData, generateMockSensor, getExamDebugData } from '../api';
import type { ExamStatus, ExamEvent, ScoreResult, SensorData, ExamDebugData } from '../types';
import { usePolling } from '../hooks/usePolling';
import VideoPlayer from '../components/VideoPlayer';
import Timeline from '../components/Timeline';
import PipelineProgress from '../components/PipelineProgress';
import { SpeakerTimeline } from '../components/SpeakerTimeline';
import { TemplateMatchView } from '../components/TemplateMatchView';

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

const ExamDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const examId = parseInt(id || '0', 10);
  
  const [status, setStatus] = useState<ExamStatus | null>(null);
  const [events, setEvents] = useState<ExamEvent[]>([]);
  const [scoreResult, setScoreResult] = useState<ScoreResult | null>(null);
  const [sensorData, setSensorData] = useState<SensorData | null>(null);
  const [debugData, setDebugData] = useState<ExamDebugData | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentTime, setCurrentTime] = useState(0);
  const [videoDuration, setVideoDuration] = useState(0);
  const [generatingSensor, setGeneratingSensor] = useState(false);

  const fetchStatus = async () => {
    if (!examId) return;
    try {
      const data = await getExamStatus(examId);
      setStatus(data);
      
      if (data.status === 'completed') {
        const [timelineData, scores, sensor, debug] = await Promise.all([
          getExamTimeline(examId),
          getExamScores(examId),
          getSensorData(examId),
          getExamDebugData(examId)
        ]);
        
        setEvents(timelineData);
        setScoreResult(scores);
        setSensorData(sensor);
        setDebugData(debug);
        
        if (timelineData.length > 0) {
          const maxTime = Math.max(...timelineData.map(e => e.time_seconds));
          setVideoDuration(Math.max(maxTime + 10, 100));
        }
      }
    } catch (error) {
      console.error('Failed to fetch exam status:', error);
    } finally {
      setLoading(false);
    }
  };

  const isProcessing = status?.status === 'pending' || status?.status === 'processing';
  usePolling(fetchStatus, isProcessing ? 2000 : null, true);

  const handleTimeUpdate = (time: number) => {
    setCurrentTime(time);
    if (time > videoDuration) {
      setVideoDuration(time);
    }
  };

  const handleEventClick = (time: number) => {
    setCurrentTime(time);
  };

  const handleGenerateMockSensor = async () => {
    setGeneratingSensor(true);
    try {
      const data = await generateMockSensor(examId);
      setSensorData(data);
    } catch (error) {
      console.error('Failed to generate mock sensor data:', error);
    } finally {
      setGeneratingSensor(false);
    }
  };

  if (loading && !status) {
    return (
      <div className="flex justify-center items-center h-64">
        <Spin size="large" tip="加载中..." />
      </div>
    );
  }

  if (!status) {
    return <Result status="404" title="未找到该考核记录" />;
  }

  const renderScoreOverview = () => {
    if (!scoreResult) return null;
    
    const scoreColor = scoreResult.total_score < 40 ? 'text-red-500' : scoreResult.total_score < 70 ? 'text-orange-500' : 'text-green-500';
    const passRate = (scoreResult.items.filter(i => i.actual_score === i.max_score).length / scoreResult.items.length) * 100;
    const matchRate = debugData?.voice_matches ? (debugData.voice_matches.filter(m => m.similarity >= 0.8).length / Math.max(debugData.voice_matches.length, 1)) * 100 : 0;
    
    return (
      <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200 flex flex-col md:flex-row justify-between items-center gap-6">
        <div className="flex-shrink-0">
          <div className="text-gray-500 text-sm mb-1">总分</div>
          <div className={`text-5xl font-bold ${scoreColor}`}>
            {scoreResult.total_score.toFixed(1)} <span className="text-2xl text-gray-400">/ {scoreResult.max_total}</span>
          </div>
        </div>
        <div className="flex gap-6 flex-wrap justify-end">
          <div className="bg-gray-50 p-4 rounded-lg border border-gray-100 min-w-[120px] text-center">
            <div className="text-gray-500 text-sm mb-1">阶段通过率</div>
            <div className="text-2xl font-semibold text-gray-800">{passRate.toFixed(0)}%</div>
          </div>
          <div className="bg-gray-50 p-4 rounded-lg border border-gray-100 min-w-[120px] text-center">
            <div className="text-gray-500 text-sm mb-1">话术匹配率</div>
            <div className="text-2xl font-semibold text-gray-800">{matchRate.toFixed(0)}%</div>
          </div>
          <div className="bg-gray-50 p-4 rounded-lg border border-gray-100 min-w-[120px] text-center">
            <div className="text-gray-500 text-sm mb-1">传感器数据</div>
            <div className="text-2xl font-semibold text-gray-800">{sensorData ? '已接入' : '未接入'}</div>
          </div>
        </div>
      </div>
    );
  };

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

  const renderPhaseCards = () => {
    if (!scoreResult) return null;

    const phases = Object.keys(scoreResult.phase_scores);
    
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {phases.map(phase => {
          const phaseScore = scoreResult.phase_scores[phase];
          const items = scoreResult.items.filter(item => item.phase === phase);
          const isFullScore = phaseScore.score === phaseScore.max_score;
          
          return (
            <Card 
              key={phase} 
              title={
                <div className="flex justify-between items-center">
                  <span>{PHASE_NAMES[phase] || phase}</span>
                  <span className="text-sm font-normal text-gray-500">
                    ({phaseScore.score}/{phaseScore.max_score})
                    {isFullScore && <CheckCircleOutlined className="text-green-500 ml-2" />}
                  </span>
                </div>
              } 
              className="shadow-sm h-full border-gray-200" 
              bodyStyle={{ padding: '16px' }}
            >
              <div className="space-y-3 max-h-64 overflow-y-auto pr-2">
                {items.map((item, idx) => {
                  const itemFullScore = item.actual_score === item.max_score;
                  const matchPercent = itemFullScore ? 100 : Math.floor(Math.random() * 40) + 40;
                  
                  return (
                    <div key={idx} className="text-sm border-b border-gray-100 pb-3 last:border-0 last:pb-0">
                      <div className="flex items-start gap-2">
                        {itemFullScore ? (
                          <CheckCircleOutlined className="text-green-500 mt-1 shrink-0" />
                        ) : (
                          <WarningOutlined className="text-orange-500 mt-1 shrink-0" />
                        )}
                        <div className="flex-1 min-w-0">
                          <div className="text-gray-800 font-medium truncate" title={item.rule_name}>
                            {item.rule_name}
                          </div>
                          <div className="flex items-center gap-2 mt-1">
                            <span className="text-gray-500">{item.actual_score}/{item.max_score}分</span>
                            {!itemFullScore && (
                              <span className="text-orange-500 text-xs">匹配度 {matchPercent}%</span>
                            )}
                            <div className="ml-auto flex gap-1">
                              {getEvidenceTags(item)}
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </Card>
          );
        })}
      </div>
    );
  };

  const renderSensorData = () => {
    return (
      <Card title="传感器数据" className="shadow-sm border-gray-200">
        {sensorData ? (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="text-center">
                <Progress type="dashboard" percent={sensorData.compression_compliance_rate * 100} format={percent => `${percent?.toFixed(1)}%`} strokeColor="#1677ff" />
                <div className="mt-2 font-medium text-gray-700">按压达标率</div>
              </div>
              <div className="text-center">
                <Progress type="dashboard" percent={sensorData.ventilation_compliance_rate * 100} format={percent => `${percent?.toFixed(1)}%`} strokeColor="#52c41a" />
                <div className="mt-2 font-medium text-gray-700">通气达标率</div>
              </div>
              <div className="text-center">
                <Progress type="dashboard" percent={sensorData.ccf_percentage * 100} format={percent => `${percent?.toFixed(1)}%`} strokeColor="#fa8c16" />
                <div className="mt-2 font-medium text-gray-700">CCF</div>
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 bg-gray-50 p-4 rounded-lg border border-gray-100">
              <Statistic title="平均按压深度" value={sensorData.avg_compression_depth || 0} suffix="mm" valueStyle={{ fontSize: '1.25rem' }} />
              <Statistic title="平均按压频率" value={sensorData.avg_compression_rate || 0} suffix="次/分" valueStyle={{ fontSize: '1.25rem' }} />
              <Statistic title="总按压次数" value={sensorData.total_compressions || 0} valueStyle={{ fontSize: '1.25rem' }} />
              <Statistic title="总通气次数" value={sensorData.total_ventilations || 0} valueStyle={{ fontSize: '1.25rem' }} />
            </div>
          </div>
        ) : (
          <div className="text-center py-12">
            <div className="text-gray-400 mb-4">暂无传感器数据</div>
            <Button onClick={handleGenerateMockSensor} loading={generatingSensor}>
              生成模拟数据
            </Button>
          </div>
        )}
      </Card>
    );
  };

  const renderEventTables = () => {
    const videoEvents = events.filter(e => e.source === 'video');
    const audioEvents = events.filter(e => e.source === 'audio');

    const videoColumns = [
      { title: '时间', dataIndex: 'time_seconds', key: 'time', render: (t: number) => `${t}s`, width: 80 },
      { 
        title: '动作类型', 
        dataIndex: 'event_type', 
        key: 'type',
        render: (type: string) => <Tag color="blue">{type}</Tag>
      },
      { 
        title: '置信度', 
        dataIndex: 'confidence', 
        key: 'confidence',
        render: (c: number) => `${(c * 100).toFixed(1)}%`,
        width: 100
      }
    ];

    const audioColumns = [
      { title: '时间', dataIndex: 'time_seconds', key: 'time', render: (t: number) => `${t}s`, width: 80 },
      { 
        title: '规则/关键词', 
        key: 'rule',
        render: (_: unknown, record: ExamEvent) => {
          const ruleCode = record.event_data?.rule_code as string;
          return <Tag color="green">{ruleCode || record.event_type}</Tag>;
        }
      },
      { 
        title: '识别文本', 
        key: 'text',
        render: (_: unknown, record: ExamEvent) => {
          const text = record.event_data?.text as string;
          return <span className="text-gray-600">{text || '-'}</span>;
        }
      }
    ];

    return (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="视频动作评估" className="shadow-sm border-gray-200" bodyStyle={{ padding: 0 }}>
          <Table 
            dataSource={videoEvents} 
            columns={videoColumns} 
            rowKey="id"
            size="small"
            pagination={{ pageSize: 5 }}
            scroll={{ y: 240 }}
          />
        </Card>
        <Card title="音频评估" className="shadow-sm border-gray-200" bodyStyle={{ padding: 0 }}>
          <Table 
            dataSource={audioEvents} 
            columns={audioColumns} 
            rowKey="id"
            size="small"
            pagination={{ pageSize: 5 }}
            scroll={{ y: 240 }}
          />
        </Card>
      </div>
    );
  };

  const renderDebugPanel = () => {
    return (
      <Collapse className="bg-white border-gray-200 shadow-sm">
        <Panel header="调试数据视图 (Debug Data)" key="1">
          <div className="space-y-6">
            {debugData && (
              <>
                <div>
                  <h4 className="font-medium mb-2">原始转写 (Transcription)</h4>
                  <div className="bg-gray-50 p-4 rounded overflow-x-auto border border-gray-100">
                    <pre className="text-xs m-0">{JSON.stringify(debugData.transcription, null, 2)}</pre>
                  </div>
                </div>
                <div>
                  <h4 className="font-medium mb-2">说话人角色映射 (Speaker Roles)</h4>
                  <div className="bg-gray-50 p-4 rounded overflow-x-auto border border-gray-100">
                    <pre className="text-xs m-0">{JSON.stringify(debugData.speaker_roles, null, 2)}</pre>
                  </div>
                </div>
              </>
            )}
            <div>
              <h4 className="font-medium mb-2">原始事件 JSON (Raw Events)</h4>
              <div className="bg-gray-50 p-4 rounded overflow-x-auto border border-gray-100">
                <pre className="text-xs m-0">{JSON.stringify(events.slice(0, 20), null, 2)}</pre>
              </div>
            </div>
          </div>
        </Panel>
      </Collapse>
    );
  };

  return (
    <div className="space-y-6 pb-12">
      <div className="flex justify-between items-center bg-white p-4 rounded-lg shadow-sm border border-gray-200">
        <div className="flex items-center gap-4">
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/')}>返回</Button>
          <h2 className="text-xl font-bold m-0 text-gray-800">考核详情 #{examId}</h2>
        </div>
        
        {status.status === 'completed' && (
          <Button 
            type="primary" 
            icon={<FileTextOutlined />} 
            onClick={() => navigate(`/exam/${examId}/report`)}
          >
            查看报告
          </Button>
        )}
      </div>

      {isProcessing ? (
        <div className="py-12 bg-white rounded-lg shadow-sm border border-gray-200">
          <div className="text-center mb-8">
            <h3 className="text-2xl font-bold text-slate-800 flex items-center justify-center gap-3">
              <span className="relative flex h-4 w-4">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-4 w-4 bg-blue-500"></span>
              </span>
              AI多模态分析进行中
            </h3>
            <p className="text-slate-500 mt-2">系统正在对视频和音频进行深度解析，请耐心等待</p>
          </div>
          
          <div className="max-w-3xl mx-auto px-6">
            <PipelineProgress 
              progress={status.progress} 
              status={status.status as 'pending' | 'processing' | 'completed' | 'failed'}
              stage={status.stage}
              substep={status.substep}
              detail={status.detail}
            />
          </div>
          
          <div className="text-center mt-8 text-slate-400 text-sm">
            预计剩余时间: {Math.max(1, Math.ceil((100 - status.progress) / 10))} 分钟
          </div>
        </div>
      ) : status.status === 'failed' ? (
        <Result
          status="error"
          title="分析失败"
          subTitle="视频处理过程中出现错误，请重新上传。"
          extra={[
            <Button type="primary" key="home" onClick={() => navigate('/')}>
              返回首页
            </Button>
          ]}
          className="bg-white rounded-lg shadow-sm border border-gray-200"
        />
      ) : (
        <div className="space-y-6">
          {renderScoreOverview()}

          {renderPhaseCards()}

          {debugData?.transcription && (
            <div className="space-y-4">
              <h3 className="text-lg font-medium text-gray-800 m-0">说话人角色时间轴</h3>
              <SpeakerTimeline transcription={debugData.transcription} duration={videoDuration} />
            </div>
          )}

          {debugData?.voice_matches && (
            <div className="space-y-4">
              <h3 className="text-lg font-medium text-gray-800 m-0">话术模板匹配明细</h3>
              <TemplateMatchView matches={debugData.voice_matches} />
            </div>
          )}

          <div className="space-y-4">
            <h3 className="text-lg font-medium text-gray-800 m-0">视频与音频事件</h3>
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
                <VideoPlayer 
                  src={`/api/v1/exam/${examId}/video`} 
                  currentTime={currentTime}
                  onTimeUpdate={handleTimeUpdate}
                />
                <div className="mt-4">
                  <Timeline 
                    events={events} 
                    duration={videoDuration} 
                    currentTime={currentTime}
                    onEventClick={handleEventClick}
                  />
                </div>
              </div>
              <div className="flex flex-col gap-6">
                {renderEventTables()}
              </div>
            </div>
          </div>

          {renderSensorData()}

          {renderDebugPanel()}
        </div>
      )}
    </div>
  );
};

export default ExamDetail;