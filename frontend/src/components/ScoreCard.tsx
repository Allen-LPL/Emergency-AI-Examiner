import React from 'react'
import { Progress } from 'antd'

interface ScoreCardProps {
  totalScore: number
  maxScore: number
}

const ScoreCard: React.FC<ScoreCardProps> = ({ totalScore, maxScore }) => {
  const percent = Math.round((totalScore / maxScore) * 100)
  
  let strokeColor = '#52c41a'
  if (percent < 60) {
    strokeColor = '#ff4d4f'
  } else if (percent < 80) {
    strokeColor = '#faad14'
  }

  return (
    <div className="flex flex-col items-center justify-center p-6 bg-white rounded-lg shadow-sm border border-gray-100">
      <h3 className="text-lg font-medium text-gray-600 mb-4">总分</h3>
      <Progress 
        type="dashboard" 
        percent={percent} 
        format={() => `${totalScore}分`}
        strokeColor={strokeColor}
        size={160}
      />
      <div className="mt-4 text-gray-500">
        满分: {maxScore}分
      </div>
    </div>
  )
}

export default ScoreCard
