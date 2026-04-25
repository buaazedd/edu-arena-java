package com.edu.arena.service;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.edu.arena.dto.request.AdminVoteQuery;
import com.edu.arena.dto.response.AdminVoteItemVO;

/**
 * 后台投票记录查询服务（admin 专用，无脱敏）。
 */
public interface VoteQueryService {

    IPage<AdminVoteItemVO> pageVotes(AdminVoteQuery query);
}
