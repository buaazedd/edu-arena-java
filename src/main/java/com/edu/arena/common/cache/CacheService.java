package com.edu.arena.common.cache;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

/**
 * 统一缓存服务
 * 管理所有缓存Key、TTL和一致性策略
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class CacheService {

    private final RedisTemplate<String, Object> redisTemplate;

    // ==================== 缓存Key定义 ====================
    
    /** 排行榜缓存 */
    public static final String LEADERBOARD_KEY = "edu_arena:leaderboard:all";
    /** ELO历史缓存 */
    public static final String ELO_HISTORY_KEY = "edu_arena:leaderboard:elo_history";
    /** 活跃模型列表 */
    public static final String ACTIVE_MODELS_KEY = "edu_arena:models:active";
    
    /** 用户信息缓存 key: userId */
    public static final String USER_KEY_PREFIX = "edu_arena:user:";
    /** 对战详情缓存 key: battleId */
    public static final String BATTLE_KEY_PREFIX = "edu_arena:battle:";
    /** 模型详情缓存 key: modelId */
    public static final String MODEL_DETAIL_KEY_PREFIX = "edu_arena:model:detail:";
    /** API模型信息缓存 key: modelId */
    public static final String API_MODEL_INFO_KEY_PREFIX = "edu_arena:api:model_info:";
    
    /** 统计计数器 */
    public static final String STATS_TOTAL_BATTLES = "edu_arena:stats:total_battles";
    public static final String STATS_TOTAL_VOTES = "edu_arena:stats:total_votes";
    public static final String STATS_DAILY_BATTLES = "edu_arena:stats:daily_battles:";
    
    /** 用户限流 key: userId */
    public static final String RATE_LIMIT_KEY_PREFIX = "edu_arena:rate_limit:user:";

    // ==================== TTL定义 (秒) ====================
    
    /** 短期缓存: 2分钟 */
    public static final long TTL_SHORT = 120;
    /** 中期缓存: 5分钟 */
    public static final long TTL_MEDIUM = 300;
    /** 长期缓存: 30分钟 */
    public static final long TTL_LONG = 1800;
    /** API缓存: 1小时 */
    public static final long TTL_API = 3600;
    /** 限流: 24小时 */
    public static final long TTL_RATE_LIMIT = 86400;

    // ==================== 通用缓存操作 ====================

    /**
     * 获取缓存，不存在则加载并缓存
     */
    @SuppressWarnings("unchecked")
    public <T> T getOrLoad(String key, long ttl, Supplier<T> loader) {
        try {
            Object cached = redisTemplate.opsForValue().get(key);
            if (cached != null) {
                log.debug("Cache hit: {}", key);
                return (T) cached;
            }
        } catch (Exception e) {
            log.warn("Redis read failed for key {}: {}", key, e.getMessage());
        }

        log.debug("Cache miss: {}", key);
        T value = loader.get();
        if (value != null) {
            set(key, value, ttl);
        }
        return value;
    }

    /**
     * 设置缓存
     */
    public void set(String key, Object value, long ttl) {
        try {
            redisTemplate.opsForValue().set(key, value, ttl, TimeUnit.SECONDS);
            log.debug("Cache set: {}, ttl={}s", key, ttl);
        } catch (Exception e) {
            log.warn("Redis write failed for key {}: {}", key, e.getMessage());
        }
    }

    /**
     * 删除缓存
     */
    public void delete(String key) {
        try {
            redisTemplate.delete(key);
            log.debug("Cache deleted: {}", key);
        } catch (Exception e) {
            log.warn("Redis delete failed for key {}: {}", key, e.getMessage());
        }
    }

    /**
     * 批量删除缓存 (支持通配符)
     */
    public void deleteByPattern(String pattern) {
        try {
            var keys = redisTemplate.keys(pattern);
            if (keys != null && !keys.isEmpty()) {
                redisTemplate.delete(keys);
                log.debug("Cache deleted by pattern: {}, count={}", pattern, keys.size());
            }
        } catch (Exception e) {
            log.warn("Redis delete by pattern failed for {}: {}", pattern, e.getMessage());
        }
    }

    // ==================== 用户缓存 ====================

    public String getUserKey(Long userId) {
        return USER_KEY_PREFIX + userId;
    }

    public void cacheUser(Long userId, Object user) {
        set(getUserKey(userId), user, TTL_LONG);
    }

    public void invalidateUser(Long userId) {
        delete(getUserKey(userId));
    }

    // ==================== 对战缓存 ====================

    public String getBattleKey(Long battleId) {
        return BATTLE_KEY_PREFIX + battleId;
    }

    public void cacheBattle(Long battleId, Object battle) {
        set(getBattleKey(battleId), battle, TTL_SHORT);
    }

    public void invalidateBattle(Long battleId) {
        delete(getBattleKey(battleId));
    }

    // ==================== 模型缓存 ====================

    public String getModelDetailKey(Long modelId) {
        return MODEL_DETAIL_KEY_PREFIX + modelId;
    }

    public void cacheModelDetail(Long modelId, Object model) {
        set(getModelDetailKey(modelId), model, TTL_MEDIUM);
    }

    public void invalidateModelDetail(Long modelId) {
        delete(getModelDetailKey(modelId));
    }

    /**
     * 清除所有模型相关缓存 (当模型信息变更时)
     */
    public void invalidateAllModelCaches() {
        delete(ACTIVE_MODELS_KEY);
        delete(LEADERBOARD_KEY);
        delete(ELO_HISTORY_KEY);
        deleteByPattern(MODEL_DETAIL_KEY_PREFIX + "*");
        log.info("All model caches invalidated");
    }

    // ==================== 统计计数器 ====================

    /**
     * 原子递增计数器
     */
    public Long increment(String key) {
        try {
            return redisTemplate.opsForValue().increment(key);
        } catch (Exception e) {
            log.warn("Redis increment failed for key {}: {}", key, e.getMessage());
            return null;
        }
    }

    /**
     * 原子递增指定值
     */
    public Long incrementBy(String key, long delta) {
        try {
            return redisTemplate.opsForValue().increment(key, delta);
        } catch (Exception e) {
            log.warn("Redis incrementBy failed for key {}: {}", key, e.getMessage());
            return null;
        }
    }

    /**
     * 获取计数器值
     */
    public Long getCounter(String key) {
        try {
            Object value = redisTemplate.opsForValue().get(key);
            if (value instanceof Number) {
                return ((Number) value).longValue();
            }
            return null;
        } catch (Exception e) {
            log.warn("Redis getCounter failed for key {}: {}", key, e.getMessage());
            return null;
        }
    }

    /**
     * 初始化计数器 (如果不存在)
     */
    public void initCounterIfAbsent(String key, long initialValue) {
        try {
            if (redisTemplate.opsForValue().get(key) == null) {
                redisTemplate.opsForValue().set(key, initialValue);
                log.debug("Counter initialized: {} = {}", key, initialValue);
            }
        } catch (Exception e) {
            log.warn("Redis initCounter failed for key {}: {}", key, e.getMessage());
        }
    }

    // ==================== 限流 ====================

    /**
     * 检查并增加用户今日对战次数
     * @return 当前次数，-1表示失败
     */
    public int checkAndIncrementUserBattleLimit(Long userId, int dailyLimit) {
        String key = RATE_LIMIT_KEY_PREFIX + userId;
        try {
            Long current = getCounter(key);
            if (current == null) {
                // 首次访问，设置过期时间到当天结束
                redisTemplate.opsForValue().set(key, 1L, TTL_RATE_LIMIT, TimeUnit.SECONDS);
                return 1;
            }
            if (current >= dailyLimit) {
                return current.intValue();
            }
            return increment(key).intValue();
        } catch (Exception e) {
            log.warn("Rate limit check failed for user {}: {}", userId, e.getMessage());
            return -1;
        }
    }

    /**
     * 获取用户今日对战次数
     */
    public int getUserBattleCountToday(Long userId) {
        Long count = getCounter(RATE_LIMIT_KEY_PREFIX + userId);
        return count != null ? count.intValue() : 0;
    }

    // ==================== API缓存 ====================

    public String getApiModelInfoKey(String modelId) {
        return API_MODEL_INFO_KEY_PREFIX + modelId;
    }

    public void cacheApiModelInfo(String modelId, Object info) {
        set(getApiModelInfoKey(modelId), info, TTL_API);
    }

    public void invalidateApiModelInfo(String modelId) {
        delete(getApiModelInfoKey(modelId));
    }

    // ==================== 排行榜相关 ====================

    /**
     * 清除排行榜和ELO历史缓存
     */
    public void invalidateLeaderboard() {
        delete(LEADERBOARD_KEY);
        delete(ELO_HISTORY_KEY);
        log.info("Leaderboard cache invalidated");
    }

    /**
     * 清除活跃模型列表
     */
    public void invalidateActiveModels() {
        delete(ACTIVE_MODELS_KEY);
    }
}
