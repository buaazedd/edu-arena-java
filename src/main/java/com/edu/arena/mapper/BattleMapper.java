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

    @Select("SELECT b.id, t.essay_title AS essayTitle, t.grade_level AS gradeLevel, " +
            "ma.name AS modelA, mb.name AS modelB, " +
            "CASE WHEN v.winner = 'A' THEN ma.name WHEN v.winner = 'B' THEN mb.name ELSE '平局' END AS winner, " +
            "b.match_type AS matchType, b.created_at AS createdAt, " +
            "v.user_id AS voterUserId, u.username AS voterUsername, u.display_name AS voterDisplayName " +
            "FROM battles b " +
            "JOIN tasks t ON b.task_id = t.id " +
            "JOIN models ma ON b.model_a_id = ma.id " +
            "JOIN models mb ON b.model_b_id = mb.id " +
            // 子查询取最早一条投票记录作为该对战的「主投票人」，保证 id/username/display_name 三字段来自同一行
            "LEFT JOIN votes v ON v.id = (SELECT MIN(v2.id) FROM votes v2 WHERE v2.battle_id = b.id) " +
            "LEFT JOIN users u ON u.id = v.user_id " +
            "WHERE b.status = 'voted' " +
            "ORDER BY b.created_at DESC")
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
