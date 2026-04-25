package com.edu.arena.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.edu.arena.dto.response.AdminVoteItemVO;
import com.edu.arena.entity.Vote;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.time.LocalDate;

/**
 * 投票Mapper
 */
@Mapper
public interface VoteMapper extends BaseMapper<Vote> {

    @Select("SELECT winner FROM votes WHERE battle_id = #{battleId} LIMIT 1")
    String selectWinnerByBattleId(Long battleId);

    /**
     * 后台投票记录分页查询（admin 专用，无脱敏）。
     *
     * <p>过滤条件均可空；空值等价于不过滤。日期按"创建时间"闭区间，
     * endDate 实际下推到次日 00:00:00（不含）以覆盖当日全天。</p>
     */
    @Select("<script>" +
            "SELECT v.id AS voteId, v.battle_id AS battleId, " +
            "       v.user_id AS voterUserId, u.username AS voterUsername, u.display_name AS voterDisplayName, " +
            "       COALESCE(NULLIF(u.display_name, ''), u.username) AS voter, " +
            "       t.essay_title AS essayTitle, t.grade_level AS gradeLevel, " +
            "       ma.name AS modelA, mb.name AS modelB, " +
            "       v.winner AS winner, " +
            "       CASE WHEN v.winner = 'A' THEN ma.name WHEN v.winner = 'B' THEN mb.name ELSE '平局' END AS winnerLabel, " +
            "       v.dim_theme AS dimTheme, v.dim_imagination AS dimImagination, " +
            "       v.dim_logic AS dimLogic, v.dim_language AS dimLanguage, " +
            "       v.dim_writing AS dimWriting, v.dim_overall AS dimOverall, " +
            "       v.vote_time AS voteTime, v.created_at AS createdAt " +
            "FROM votes v " +
            "LEFT JOIN users u ON u.id = v.user_id " +
            "LEFT JOIN battles b ON b.id = v.battle_id " +
            "LEFT JOIN tasks t ON t.id = b.task_id " +
            "LEFT JOIN models ma ON ma.id = b.model_a_id " +
            "LEFT JOIN models mb ON mb.id = b.model_b_id " +
            "<where>" +
            "  <if test='userId != null'> AND v.user_id = #{userId} </if>" +
            "  <if test='battleId != null'> AND v.battle_id = #{battleId} </if>" +
            "  <if test='keyword != null and keyword != \"\"'> " +
            "    AND (u.username LIKE CONCAT('%', #{keyword}, '%') " +
            "         OR u.display_name LIKE CONCAT('%', #{keyword}, '%')) " +
            "  </if>" +
            "  <if test='startDate != null'> AND v.created_at &gt;= #{startDate} </if>" +
            "  <if test='endDate != null'> AND v.created_at &lt; DATE_ADD(#{endDate}, INTERVAL 1 DAY) </if>" +
            "</where>" +
            " ORDER BY v.created_at DESC" +
            "</script>")
    IPage<AdminVoteItemVO> selectVotePage(Page<AdminVoteItemVO> page,
                                          @Param("userId") Long userId,
                                          @Param("battleId") Long battleId,
                                          @Param("keyword") String keyword,
                                          @Param("startDate") LocalDate startDate,
                                          @Param("endDate") LocalDate endDate);

}
