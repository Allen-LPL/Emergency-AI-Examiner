import React from 'react'
import { Layout as AntLayout, Menu } from 'antd'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { VideoCameraOutlined, HomeOutlined } from '@ant-design/icons'

const { Header, Content, Footer } = AntLayout

const Layout: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()

  // 临时去除登录注册：隐藏登录/退出按钮，仅保留主导航
  const menuItems = [
    {
      key: '/',
      icon: <HomeOutlined />,
      label: '首页',
    },
  ]

  return (
    <AntLayout className="min-h-screen">
      <Header className="flex items-center justify-between bg-white px-6 shadow-sm z-10">
        <div className="flex items-center gap-2 cursor-pointer" onClick={() => navigate('/')}>
          <VideoCameraOutlined className="text-blue-600 text-2xl" />
          <span className="text-xl font-bold text-gray-800">急救AI考官系统</span>
        </div>

        <div className="flex items-center gap-6">
          <Menu
            mode="horizontal"
            selectedKeys={[location.pathname]}
            items={menuItems}
            onClick={({ key }) => navigate(key)}
            className="border-none min-w-[200px]"
          />
        </div>
      </Header>
      
      <Content className="p-6 max-w-7xl mx-auto w-full">
        <div className="bg-white p-6 rounded-lg shadow-sm min-h-[calc(100vh-134px)]">
          <Outlet />
        </div>
      </Content>
      
      <Footer className="text-center text-gray-500">
        急救AI考官系统 ©{new Date().getFullYear()}
      </Footer>
    </AntLayout>
  )
}

export default Layout
