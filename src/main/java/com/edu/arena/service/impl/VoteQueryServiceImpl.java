package com.edu.arena.service.impl;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.edu.arena.dto.request.AdminVoteQuery;
import com.edu.arena.dto.response.AdminVoteItemVO;
import com.edu.arena.mapper.VoteMapper;
import com.edu.arena.service.VoteQueryService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

/**
 * 后台投票记录查询实现。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class VoteQueryServiceImpl implements VoteQueryService {

    private final VoteMapper voteMapper;

    @Override
    public IPage<AdminVoteItemVO> pageVotes(AdminVoteQuery query) {
        int page = query.getPage() != null && query.getPage() > 0 ? query.getPage() : 1;
        int size = query.getSize() != null && query.getSize() > 0 && query.getSize() <= 200
                ? query.getSize() : 20;
        Page<AdminVoteItemVO> pager = new Page<>(page, size);
        String keyword = query.getKeyword();
        if (keyword != null) {
            keyword = keyword.trim();
            if (keyword.isEmpty()) {
                keyword = null;
            }
        }
        return voteMapper.selectVotePage(
                pager,
                query.getUserId(),
                query.getBattleId(),
                keyword,
                query.getStartDate(),
                query.getEndDate()
        );
    }
}
