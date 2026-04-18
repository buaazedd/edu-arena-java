package com.edu.arena.dto.response;

import lombok.Data;

/**
 * 模型测试结果
 */
@Data
public class ModelProbeResultVO {

    /**
     * 数据库模型ID
     */
    private Long id;

    /**
     * 平台模型ID
     */
    private String modelId;

    /**
     * 模型名称
     */
    private String name;

    /**
     * 是否声明支持图片输入
     */
    private Boolean supportsImageInput;

    /**
     * 是否调用成功
     */
    private Boolean success;

    /**
     * 调用耗时
     */
    private Long latencyMs;

    /**
     * 测试图片数量
     */
    private Integer imageCount;

    /**
     * 返回内容预览
     */
    private String responsePreview;

    /**
     * 错误信息
     */
    private String errorMessage;
}
