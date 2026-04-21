package com.edu.arena.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;
import lombok.ToString;

import java.util.List;

/**
 * 创建对战请求
 */
@Data
public class CreateBattleRequest {

    /**
     * 作文题目（材料作文可能很长，不限制字数）
     */
    @NotBlank(message = "题目不能为空")
    private String essayTitle;

    /**
     * 作文内容
     */
    @Size(max = 50000, message = "作文内容最多50000字符")
    private String essayContent;

    /**
     * 年级
     */
    @Size(max = 20, message = "年级最多20字符")
    private String gradeLevel = "初中";

    /**
     * 批改要求
     */
    @Size(max = 1000, message = "批改要求最多1000字符")
    private String requirements;

    /**
     * 图片列表(纯Base64字符串，不含data:image前缀)
     * 单张图片大小限制：20MB
     * 支持格式：PNG, JPEG, WEBP
     * 最大数量：10张
     */
    @Size(max = 10, message = "最多上传10张图片")
    @ToString.Exclude
    private List<String> images;

}
