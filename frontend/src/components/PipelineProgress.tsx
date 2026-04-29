import React, { useState, useEffect } from 'react';
import { 
  UploadOutlined, 
  VideoCameraOutlined, 
  AudioOutlined, 
  MergeCellsOutlined, 
  TrophyOutlined,
  CheckCircleFilled,
  CloseCircleFilled,
  LoadingOutlined
} from '@ant-design/icons';

interface PipelineProgressProps {
  progress: number;
  status: 'pending' | 'processing' | 'completed' | 'failed';
}

interface StageConfig {
  id: number;
  title: string;
  description: string;
  icon: React.ReactNode;
  progressRange: [number, number];
  subSteps: string[];
}

const STAGES: StageConfig[] = [
  {
    id: 1,
    title: '视频上传',
    description: '视频文件接收与存储',
    icon: <UploadOutlined />,
    progressRange: [0, 10],
    subSteps: ['正在接收文件...', '保存到存储系统...', '验证文件完整性...']
  },
  {
    id: 2,
    title: '视频分析',
    description: 'YOLOv8人体检测 + ByteTrack多人跟踪 + 姿态估计 + 动作识别',
    icon: <VideoCameraOutlined />,
    progressRange: [10, 40],
    subSteps: ['正在提取视频帧...', 'YOLOv8人体检测中...', 'ByteTrack多人跟踪...', '姿态估计分析...', '动作识别处理...']
  },
  {
    id: 3,
    title: '音频分析',
    description: 'FunASR语音识别 + 说话人分离 + 关键词匹配',
    icon: <AudioOutlined />,
    progressRange: [40, 60],
    subSteps: ['提取音频轨道...', '语音活动检测...', 'FunASR语音识别...', '说话人分离...', '关键词匹配...']
  },
  {
    id: 4,
    title: '多模态融合',
    description: '视频+音频事件合并 + 统一时间轴构建',
    icon: <MergeCellsOutlined />,
    progressRange: [60, 80],
    subSteps: ['合并视频事件...', '合并音频事件...', '构建统一时间轴...']
  },
  {
    id: 5,
    title: '评分计算',
    description: '6阶段规则引擎评分 + 报告生成',
    icon: <TrophyOutlined />,
    progressRange: [80, 100],
    subSteps: ['阶段一评分...', '阶段二评分...', '阶段三评分...', '生成评分报告...']
  }
];

const PipelineProgress: React.FC<PipelineProgressProps> = ({ progress, status }) => {
  const [subStepIndex, setSubStepIndex] = useState(0);

  const currentStageIndex = STAGES.findIndex(
    stage => progress >= stage.progressRange[0] && progress < stage.progressRange[1]
  );
  
  const activeStageIndex = progress >= 100 ? 4 : (currentStageIndex === -1 ? 0 : currentStageIndex);

  useEffect(() => {
    if (status !== 'processing') return;
    
    const activeStage = STAGES[activeStageIndex];
    if (!activeStage || activeStage.subSteps.length === 0) return;

    const interval = setInterval(() => {
      setSubStepIndex(prev => (prev + 1) % activeStage.subSteps.length);
    }, 2000);

    return () => clearInterval(interval);
  }, [activeStageIndex, status]);

  useEffect(() => {
    setSubStepIndex(0);
  }, [activeStageIndex]);

  return (
    <div className="w-full max-w-3xl mx-auto bg-white rounded-xl shadow-sm border border-slate-200 p-8">
      <div className="relative">
        {STAGES.map((stage, index) => {
          const isCompleted = progress >= stage.progressRange[1] || status === 'completed';
          const isActive = index === activeStageIndex && status === 'processing';
          const isFailed = index === activeStageIndex && status === 'failed';
          const isPending = progress < stage.progressRange[0] && status !== 'failed';

          let lineFill = 0;
          if (isCompleted) {
            lineFill = 100;
          } else if (isActive) {
            const range = stage.progressRange[1] - stage.progressRange[0];
            const current = progress - stage.progressRange[0];
            lineFill = Math.max(0, Math.min(100, (current / range) * 100));
          }

          return (
            <div key={stage.id} className="relative flex items-start mb-12 last:mb-0">
              {index < STAGES.length - 1 && (
                <div className="absolute left-6 top-12 bottom-[-3rem] w-0.5 bg-slate-100">
                  <div 
                    className="absolute top-0 left-0 w-full bg-orange-600 transition-all duration-500 ease-out"
                    style={{ height: `${lineFill}%` }}
                  />
                </div>
              )}

              <div className="relative z-10 flex-shrink-0 mr-6">
                <div className={`
                  w-12 h-12 rounded-full flex items-center justify-center text-xl border-2 transition-all duration-300
                  ${isCompleted ? 'bg-slate-800 border-slate-800 text-white' : ''}
                  ${isActive ? 'bg-white border-orange-600 text-orange-600 shadow-[0_0_15px_rgba(234,88,12,0.3)]' : ''}
                  ${isFailed ? 'bg-white border-red-600 text-red-600' : ''}
                  ${isPending ? 'bg-white border-slate-200 text-slate-400' : ''}
                `}>
                  {isCompleted ? <CheckCircleFilled className="text-2xl" /> : 
                   isFailed ? <CloseCircleFilled className="text-2xl" /> : 
                   stage.icon}
                </div>
                
                {isActive && (
                  <div className="absolute inset-0 rounded-full border-2 border-orange-600 animate-ping opacity-20" />
                )}
              </div>

              <div className={`flex-1 pt-2 transition-opacity duration-300 ${isPending ? 'opacity-50' : 'opacity-100'}`}>
                <div className="flex items-center justify-between mb-1">
                  <h4 className={`text-lg font-bold m-0 ${isActive ? 'text-orange-600' : 'text-slate-800'}`}>
                    {stage.title}
                  </h4>
                  <span className="text-sm font-medium text-slate-400">
                    {stage.progressRange[0]}% - {stage.progressRange[1]}%
                  </span>
                </div>
                
                <p className="text-sm text-slate-500 mb-2">
                  {stage.description}
                </p>

                {isActive && (
                  <div className="flex items-center text-sm text-orange-600 bg-orange-50 px-3 py-2 rounded-md border border-orange-100 w-fit animate-pulse">
                    <LoadingOutlined className="mr-2" />
                    <span className="transition-all duration-300">
                      {stage.subSteps[subStepIndex]}
                    </span>
                  </div>
                )}
                
                {isFailed && (
                  <div className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded-md border border-red-100 w-fit mt-2">
                    处理失败，请检查系统日志
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default PipelineProgress;
