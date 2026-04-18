package com.edu.arena.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

import java.math.BigDecimal;

/**
 * 添加模型请求
 */
@Data
public class AddModelRequest {

    /**
     * 模型ID(调用API用)
     */
    @NotBlank(message = "模型ID不能为空")
    @Size(max = 100, message = "模型ID最多100字符")
    private String modelId;

    /**
     * 模型名称
     */
    @Size(max = 100, message = "模型名称最多100字符")
    private String name;

    /**
     * 所属公司
     */
    @Size(max = 50, message = "公司名称最多50字符")
    private String company;

    /**
     * 模型描述
     */
    @Size(max = 500, message = "描述最多500字符")
    private String description;

    /**
     * 输入模态: text,image,audio,video
     */
    private String inputModalities;

    /**
     * 功能特性
     */
    private String features;

    /**
     * 上下文长度
     */
    private Integer contextLength;

    /**
     * 最大输出Token
     */
    private Integer maxOutput;

    /**
     * 输入价格
     */
    private BigDecimal inputPrice;

    /**
     * 输出价格
     */
    private BigDecimal outputPrice;

}
