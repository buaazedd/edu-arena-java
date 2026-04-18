package com.edu.arena.dto.response;

import lombok.Data;
import lombok.ToString;

import java.util.List;

/**
 * 对战详情响应
 */
@Data
public class BattleVO {

    private Long battleId;
    private String status;
    private String essayTitle;
    private String essayContent;
    private String gradeLevel;
    private String requirements;
    
    /**
     * 作文图片列表（Base64格式）
     */
    @ToString.Exclude
    private List<String> images;
    
    /**
     * 获胜方: A/B/tie (仅投票后有值)
     */
    private String winner;

    /**
     * 左侧响应(根据displayOrder可能来自A或B)
     */
    private String responseLeft;

    /**
     * 右侧响应
     */
    private String responseRight;

    /**
     * 左侧模型信息
     */
    private ModelSimpleVO modelLeft;

    /**
     * 右侧模型信息
     */
    private ModelSimpleVO modelRight;

}
