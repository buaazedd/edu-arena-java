package com.edu.arena.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.edu.arena.entity.Model;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Update;

import java.math.BigDecimal;

/**
 * 模型Mapper
 */
@Mapper
public interface ModelMapper extends BaseMapper<Model> {

    /**
     * 原子性更新ELO分数和统计数据
     * @param modelId 模型ID
     * @param newElo 新ELO分数
     * @param isWin 是否获胜
     * @param isTie 是否平局
     * @return 更新行数
     */
    @Update("UPDATE models SET elo_score = #{newElo}, " +
            "total_matches = total_matches + 1, " +
            "win_count = win_count + CASE WHEN #{isWin} THEN 1 ELSE 0 END, " +
            "lose_count = lose_count + CASE WHEN #{isWin} THEN 0 WHEN #{isTie} THEN 0 ELSE 1 END, " +
            "tie_count = tie_count + CASE WHEN #{isTie} THEN 1 ELSE 0 END, " +
            "updated_at = NOW() " +
            "WHERE id = #{modelId}")
    int updateEloAndStats(@Param("modelId") Long modelId, 
                          @Param("newElo") BigDecimal newElo, 
                          @Param("isWin") boolean isWin, 
                          @Param("isTie") boolean isTie);

}
