package com.edu.arena.service;

import com.edu.arena.dto.response.MatchResultVO;
import com.edu.arena.entity.Model;

import java.util.List;

/**
 * ELO匹配服务接口
 */
public interface EloMatchService {

    /**
     * 基于ELO匹配两个模型
     * 
     * @param candidateModels 候选模型列表（已过滤状态和图片支持）
     * @return 匹配结果
     */
    MatchResultVO matchModels(List<Model> candidateModels);

    /**
     * 获取模型在最近N场对战中的对手ID列表
     * 
     * @param modelId 模型ID
     * @param limit 查询条数
     * @return 已配对的模型ID列表
     */
    List<Long> getRecentOpponentIds(Long modelId, int limit);
}
