-- ============================================================
-- 教育大模型众包式对战评测平台 - MySQL 完整初始化脚本
-- 版本: 2.0
-- 说明: 包含所有表结构和初始数据，用于全新安装
-- ============================================================

-- 创建数据库
DROP DATABASE IF EXISTS edu_arena;
CREATE DATABASE edu_arena CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE edu_arena;

-- ============================================================
-- 1. 用户表 (users)
-- ============================================================
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL COMMENT '用户名',
    password VARCHAR(255) NOT NULL COMMENT '密码哈希(BCrypt)',
    display_name VARCHAR(100) COMMENT '显示名称',
    role ENUM('admin', 'teacher') DEFAULT 'teacher' COMMENT '角色',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    last_login TIMESTAMP NULL COMMENT '最后登录时间',
    INDEX idx_username (username),
    INDEX idx_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

-- ============================================================
-- 2. 模型表 (models) - 包含多模态支持字段
-- ============================================================
CREATE TABLE models (
    id INT AUTO_INCREMENT PRIMARY KEY,
    model_id VARCHAR(100) UNIQUE NOT NULL COMMENT 'API模型ID',
    name VARCHAR(100) NOT NULL COMMENT '显示名称',
    company VARCHAR(100) COMMENT '所属公司',
    description TEXT COMMENT '模型描述',
    input_modalities VARCHAR(100) COMMENT '输入模态: text,image,audio,video',
    features VARCHAR(255) COMMENT '功能特性: thinking,tools,function_calling等',
    context_length INT COMMENT '上下文长度',
    max_output INT COMMENT '最大输出Token',
    input_price DECIMAL(10,6) COMMENT '输入价格(每1K Token)',
    output_price DECIMAL(10,6) COMMENT '输出价格(每1K Token)',
    elo_score DECIMAL(10,2) DEFAULT 1500.00 COMMENT 'ELO分数',
    total_matches INT DEFAULT 0 COMMENT '总对战次数',
    win_count INT DEFAULT 0 COMMENT '胜利次数',
    lose_count INT DEFAULT 0 COMMENT '失败次数',
    tie_count INT DEFAULT 0 COMMENT '平局次数',
    status ENUM('active', 'inactive') DEFAULT 'active' COMMENT '状态',
    is_new TINYINT(1) DEFAULT 1 COMMENT '是否新模型',
    positioning_done TINYINT(1) DEFAULT 0 COMMENT '定位完成',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_elo (elo_score DESC),
    INDEX idx_status (status),
    INDEX idx_status_elo (status, elo_score DESC),
    INDEX idx_is_new (is_new),
    INDEX idx_input_modalities (input_modalities)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI模型表';

-- ============================================================
-- 3. 任务表 (tasks) - 包含图片支持字段
-- ============================================================
CREATE TABLE tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL COMMENT '用户ID',
    essay_title VARCHAR(500) NOT NULL COMMENT '作文题目',
    essay_content TEXT COMMENT '作文内容（可为空，图片模式下无文字内容）',
    grade_level VARCHAR(20) DEFAULT '初中' COMMENT '年级',
    requirements TEXT COMMENT '批改要求',
    has_images TINYINT(1) DEFAULT 0 COMMENT '是否有图片',
    images_json LONGTEXT COMMENT '图片Base64列表(JSON数组)',
    image_count INT DEFAULT 0 COMMENT '图片数量',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user (user_id),
    INDEX idx_grade (grade_level),
    INDEX idx_created (created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='任务表';

-- ============================================================
-- 4. 对战表 (battles)
-- ============================================================
CREATE TABLE battles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    task_id INT NOT NULL COMMENT '任务ID',
    model_a_id INT NOT NULL COMMENT '模型A ID',
    model_b_id INT NOT NULL COMMENT '模型B ID',
    display_order ENUM('normal', 'swapped') DEFAULT 'normal' COMMENT '显示顺序',
    status ENUM('generating', 'ready', 'voted', 'failed') DEFAULT 'generating' COMMENT '状态',
    match_type VARCHAR(50) DEFAULT 'normal' COMMENT '对战类型',
    response_a TEXT COMMENT '模型A回复',
    response_b TEXT COMMENT '模型B回复',
    winner ENUM('A', 'B', 'tie') COMMENT '获胜方',
    error_message TEXT COMMENT '错误信息',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (model_a_id) REFERENCES models(id),
    FOREIGN KEY (model_b_id) REFERENCES models(id),
    INDEX idx_status (status),
    INDEX idx_task (task_id),
    INDEX idx_created (created_at DESC),
    INDEX idx_match_type (match_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='对战表';

-- ============================================================
-- 5. 投票表 (votes) - 包含每个维度的理由字段
-- ============================================================
CREATE TABLE votes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    battle_id INT NOT NULL COMMENT '对战ID',
    user_id INT NOT NULL COMMENT '用户ID',
    winner ENUM('A', 'B', 'tie') NOT NULL COMMENT '总体获胜方',
    dim_theme ENUM('A', 'B', 'tie') NOT NULL COMMENT '主旨维度投票',
    dim_imagination ENUM('A', 'B', 'tie') NOT NULL COMMENT '想象维度投票',
    dim_logic ENUM('A', 'B', 'tie') NOT NULL COMMENT '逻辑维度投票',
    dim_language ENUM('A', 'B', 'tie') NOT NULL COMMENT '语言维度投票',
    dim_writing ENUM('A', 'B', 'tie') NOT NULL COMMENT '书写维度投票',
    dim_overall ENUM('A', 'B', 'tie') COMMENT '整体评价维度投票（决定最终胜负）',
    dim_theme_reason TEXT COMMENT '主旨维度评分理由',
    dim_imagination_reason TEXT COMMENT '想象维度评分理由',
    dim_logic_reason TEXT COMMENT '逻辑维度评分理由',
    dim_language_reason TEXT COMMENT '语言维度评分理由',
    dim_writing_reason TEXT COMMENT '书写维度评分理由',
    dim_overall_reason TEXT COMMENT '整体评价维度评分理由',
    vote_time DECIMAL(10,2) COMMENT '投票耗时(秒)',
    elo_a_before DECIMAL(10,2) COMMENT '投票前模型A的ELO',
    elo_b_before DECIMAL(10,2) COMMENT '投票前模型B的ELO',
    elo_a_after DECIMAL(10,2) COMMENT '投票后模型A的ELO',
    elo_b_after DECIMAL(10,2) COMMENT '投票后模型B的ELO',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    FOREIGN KEY (battle_id) REFERENCES battles(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY uk_battle_user (battle_id, user_id),
    INDEX idx_user (user_id),
    INDEX idx_battle (battle_id),
    INDEX idx_winner (winner),
    INDEX idx_created (created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='投票表';

-- ============================================================
-- 6. ELO历史表 (elo_history)
-- ============================================================
CREATE TABLE elo_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    model_id INT NOT NULL COMMENT '模型ID',
    elo_score DECIMAL(10,2) NOT NULL COMMENT 'ELO分数',
    battle_id INT COMMENT '关联的对战ID',
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '记录时间',
    FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE CASCADE,
    FOREIGN KEY (battle_id) REFERENCES battles(id) ON DELETE SET NULL,
    INDEX idx_model (model_id),
    INDEX idx_battle (battle_id),
    INDEX idx_recorded (recorded_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ELO历史记录表';

-- ============================================================
-- 7. 质量日志表 (quality_logs)
-- ============================================================
CREATE TABLE quality_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    vote_id INT COMMENT '投票ID',
    check_type VARCHAR(50) COMMENT '检查类型',
    result ENUM('warning', 'error') NOT NULL COMMENT '结果',
    detail TEXT COMMENT '详情',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    FOREIGN KEY (vote_id) REFERENCES votes(id) ON DELETE SET NULL,
    INDEX idx_check_type (check_type),
    INDEX idx_result (result)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='质量日志表';

-- ============================================================
-- 8. 图片附件表 (essay_images) - 预留，当前使用Base64存储
-- ============================================================
CREATE TABLE essay_images (
    id INT AUTO_INCREMENT PRIMARY KEY,
    task_id INT NOT NULL COMMENT '任务ID',
    filename VARCHAR(255) NOT NULL COMMENT '存储文件名',
    original_name VARCHAR(255) NOT NULL COMMENT '原始文件名',
    file_path VARCHAR(500) NOT NULL COMMENT '文件路径',
    file_size INT NOT NULL COMMENT '文件大小(字节)',
    mime_type VARCHAR(100) COMMENT 'MIME类型',
    width INT COMMENT '图片宽度',
    height INT COMMENT '图片高度',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '上传时间',
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    INDEX idx_task (task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='图片附件表';

-- ============================================================
-- 初始数据
-- ============================================================

-- 插入管理员账户
-- 默认密码: admin123 (BCrypt加密)
INSERT INTO users (username, password, display_name, role) VALUES 
('admin', '$2b$10$SSFZjP4SnNnJZWE5T4vD8.97l9c6J77D0cGBF/vSMHAjR58MQ9lE6', '系统管理员', 'admin');

-- ============================================================
-- 示例模型数据（可选，通过管理后台添加）
-- ============================================================

-- 多模态模型示例（取消注释以启用）
-- INSERT INTO models (model_id, name, company, description, input_modalities, features, context_length, max_output, input_price, output_price, elo_score, status) VALUES
-- ('gpt-4o', 'GPT-4o', 'OpenAI', 'GPT-4o is a multimodal model', 'text,image', 'thinking,function_calling,tools', 128000, 4096, 0.005, 0.015, 1500, 'active'),
-- ('claude-3-5-sonnet', 'Claude 3.5 Sonnet', 'Anthropic', 'Claude 3.5 Sonnet', 'text,image', 'thinking,tools', 200000, 8192, 0.003, 0.015, 1500, 'active'),
-- ('gemini-1.5-pro', 'Gemini 1.5 Pro', 'Google', 'Gemini 1.5 Pro', 'text,image,audio,video', 'thinking,tools,function_calling', 1000000, 8192, 0.00125, 0.005, 1500, 'active'),
-- ('qwen-vl-max', 'Qwen-VL-Max', 'Alibaba', 'Qwen Vision Language Max', 'text,image', 'tools,function_calling', 32768, 2048, 0.0005, 0.002, 1500, 'active');

-- ============================================================
-- 完成提示
-- ============================================================
SELECT '数据库初始化完成!' AS status;
SELECT CONCAT('数据库: ', DATABASE()) AS database_name;
SELECT COUNT(*) AS user_count FROM users;
