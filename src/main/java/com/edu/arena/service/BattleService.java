package com.edu.arena.service;

import com.edu.arena.dto.request.CreateBattleRequest;
import com.edu.arena.dto.request.VoteRequest;
import com.edu.arena.dto.response.BattleHistoryVO;
import com.edu.arena.dto.response.BattleVO;
import com.edu.arena.dto.response.VoteResultVO;
import com.baomidou.mybatisplus.core.metadata.IPage;


/**
 * 对战服务接口
 */
public interface BattleService {

    /**
     * 创建对战
     */
    Long createBattle(Long userId, CreateBattleRequest request);

    /**
     * 同步生成对战内容
     */
    BattleVO generateBattle(Long battleId);

    /**
     * 获取对战详情
     */
    BattleVO getBattleDetail(Long battleId);

    /**
     * 投票
     */
    VoteResultVO vote(Long userId, Long battleId, VoteRequest request);

    /**
     * 获取对战历史
     */
    IPage<BattleHistoryVO> getBattleHistory(int page, int size);

}
