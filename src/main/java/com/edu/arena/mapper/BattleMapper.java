package com.edu.arena.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.edu.arena.entity.Battle;
import com.edu.arena.dto.response.BattleHistoryVO;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

/**
 * 对战Mapper
 */
@Mapper
public interface BattleMapper extends BaseMapper<Battle> {

    @Select("SELECT * FROM (" +
            "SELECT b.id, t.essay_title as essayTitle, t.grade_level as gradeLevel, " +
            "ma.name as modelA, mb.name as modelB, " +
            "CASE WHEN MAX(v.winner) = 'A' THEN ma.name WHEN MAX(v.winner) = 'B' THEN mb.name ELSE '平局' END as winner, " +
            "b.match_type as matchType, b.created_at as createdAt " +
            "FROM battles b " +
            "JOIN tasks t ON b.task_id = t.id " +
            "JOIN models ma ON b.model_a_id = ma.id " +
            "JOIN models mb ON b.model_b_id = mb.id " +
            "LEFT JOIN votes v ON b.id = v.battle_id " +
            "WHERE b.status = 'voted' " +
            "GROUP BY b.id, t.essay_title, t.grade_level, ma.name, mb.name, b.match_type, b.created_at " +
            ") AS history ORDER BY createdAt DESC")
    IPage<BattleHistoryVO> selectHistoryPage(Page<BattleHistoryVO> page);

    /**
     * 查询最近N场对战中指定模型配对过的模型ID列表
     * @param modelId 模型ID
     * @param limit 查询条数
     * @return 已配对的模型ID列表（不重复，按最近配对时间降序）
     */
    @Select("SELECT opponent_id FROM (" +
            "SELECT model_b_id as opponent_id, created_at FROM battles WHERE model_a_id = #{modelId} " +
            "UNION ALL " +
            "SELECT model_a_id as opponent_id, created_at FROM battles WHERE model_b_id = #{modelId} " +
            ") AS paired " +
            "GROUP BY opponent_id " +
            "ORDER BY MAX(created_at) DESC " +
            "LIMIT #{limit}")
    List<Long> selectRecentOpponentIds(@Param("modelId") Long modelId, @Param("limit") int limit);

}
