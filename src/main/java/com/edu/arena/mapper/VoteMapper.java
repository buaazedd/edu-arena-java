package com.edu.arena.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.edu.arena.entity.Vote;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

/**
 * 投票Mapper
 */
@Mapper
public interface VoteMapper extends BaseMapper<Vote> {

    @Select("SELECT winner FROM votes WHERE battle_id = #{battleId} LIMIT 1")
    String selectWinnerByBattleId(Long battleId);

}
