package com.edu.arena.service.impl;

import cn.hutool.json.JSONUtil;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.edu.arena.aiclient.AiClient;
import com.edu.arena.common.cache.CacheService;
import com.edu.arena.common.exception.BusinessException;
import com.edu.arena.dto.request.AddModelRequest;
import com.edu.arena.dto.response.ModelInfoVO;
import com.edu.arena.dto.response.ModelProbeResultVO;
import com.edu.arena.entity.Battle;
import com.edu.arena.entity.Model;
import com.edu.arena.entity.Task;
import com.edu.arena.mapper.BattleMapper;
import com.edu.arena.mapper.ModelMapper;
import com.edu.arena.mapper.UserMapper;
import com.edu.arena.service.ModelService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;

@Slf4j
@Service
@RequiredArgsConstructor
public class ModelServiceImpl implements ModelService {

    private final ModelMapper modelMapper;
    private final BattleMapper battleMapper;
    private final UserMapper userMapper;
    private final AiClient aiClient;
    private final CacheService cacheService;

    @Override
    public List<Model> getAllModels() {
        return modelMapper.selectList(
                new LambdaQueryWrapper<Model>().orderByDesc(Model::getEloScore)
        );
    }

    @Override
    public void addModel(AddModelRequest request) {
        Long count = modelMapper.selectCount(
                new LambdaQueryWrapper<Model>().eq(Model::getModelId, request.getModelId())
        );
        if (count > 0) {
            throw new BusinessException("Model ID already exists");
        }

        Model model = new Model();
        model.setModelId(request.getModelId());

        ModelInfoVO modelInfo = null;
        if (aiClient.isConfigured()) {
            log.info("Fetching model info from API: {}", request.getModelId());
            modelInfo = aiClient.fetchModelInfo(request.getModelId());
            if (modelInfo == null) {
                log.warn("无法从API获取模型信息: {}，但仍允许添加", request.getModelId());
            }
        }

        if (request.getName() != null && !request.getName().isEmpty()) {
            model.setName(request.getName());
        } else if (modelInfo != null && modelInfo.getModelName() != null) {
            model.setName(modelInfo.getModelName());
        } else {
            model.setName(request.getModelId());
        }

        model.setCompany(request.getCompany() != null ? request.getCompany() : "");

        if (request.getDescription() != null && !request.getDescription().isEmpty()) {
            model.setDescription(request.getDescription());
        } else if (modelInfo != null && modelInfo.getDesc() != null) {
            model.setDescription(modelInfo.getDesc());
        }

        if (request.getInputModalities() != null && !request.getInputModalities().isEmpty()) {
            model.setInputModalities(request.getInputModalities());
        } else if (modelInfo != null && modelInfo.getInputModalities() != null) {
            model.setInputModalities(modelInfo.getInputModalities());
        }

        if (request.getFeatures() != null && !request.getFeatures().isEmpty()) {
            model.setFeatures(request.getFeatures());
        } else if (modelInfo != null && modelInfo.getFeatures() != null) {
            model.setFeatures(modelInfo.getFeatures());
        }

        if (request.getContextLength() != null) {
            model.setContextLength(request.getContextLength());
        } else if (modelInfo != null && modelInfo.getContextLength() != null) {
            model.setContextLength(modelInfo.getContextLength());
        }

        if (request.getMaxOutput() != null) {
            model.setMaxOutput(request.getMaxOutput());
        } else if (modelInfo != null && modelInfo.getMaxOutput() != null) {
            model.setMaxOutput(modelInfo.getMaxOutput());
        }

        if (request.getInputPrice() != null) {
            model.setInputPrice(request.getInputPrice());
        } else if (modelInfo != null && modelInfo.getPricing() != null && modelInfo.getPricing().getInput() != null) {
            model.setInputPrice(modelInfo.getPricing().getInput());
        }

        if (request.getOutputPrice() != null) {
            model.setOutputPrice(request.getOutputPrice());
        } else if (modelInfo != null && modelInfo.getPricing() != null && modelInfo.getPricing().getOutput() != null) {
            model.setOutputPrice(modelInfo.getPricing().getOutput());
        }

        model.setEloScore(new BigDecimal("1500"));
        model.setTotalMatches(0);
        model.setWinCount(0);
        model.setLoseCount(0);
        model.setTieCount(0);
        model.setStatus("active");
        model.setIsNew(true);
        model.setPositioningDone(false);

        modelMapper.insert(model);
        log.info("Model added: {} ({})", model.getName(), model.getModelId());
    }

    @Override
    public void toggleModelStatus(Long modelId) {
        Model model = modelMapper.selectById(modelId);
        if (model == null) {
            throw new BusinessException("Model not found");
        }
        String newStatus = "active".equals(model.getStatus()) ? "inactive" : "active";
        modelMapper.update(null,
                new LambdaUpdateWrapper<Model>()
                        .eq(Model::getId, modelId)
                        .set(Model::getStatus, newStatus)
        );
        clearActiveModelsCache();
    }

    @Override
    public List<Model> getActiveModels() {
        return cacheService.getOrLoad(
                CacheService.ACTIVE_MODELS_KEY,
                CacheService.TTL_MEDIUM,
                () -> modelMapper.selectList(
                        new LambdaQueryWrapper<Model>().eq(Model::getStatus, "active")
                )
        );
    }

    @Override
    public List<ModelProbeResultVO> probeAllModels() {
        List<Model> models = getAllModels();
        List<String> testImages = loadProbeImages();
        if (testImages.isEmpty()) {
            throw new BusinessException("测试图片不存在，请检查 src/main/resources/picture 目录");
        }

        Task probeTask = aiClient.buildProbeTask(testImages);
        List<ModelProbeResultVO> results = new ArrayList<>();

        for (Model model : models) {
            ModelProbeResultVO result = new ModelProbeResultVO();
            result.setId(model.getId());
            result.setModelId(model.getModelId());
            result.setName(model.getName());
            result.setSupportsImageInput(model.supportsImageInput());
            result.setImageCount(testImages.size());

            long start = System.currentTimeMillis();
            try {
                String response = aiClient.generate(model.getModelId(), probeTask);
                result.setSuccess(true);
                result.setResponsePreview(buildPreview(response));
                result.setErrorMessage(null);
                log.info("模型探测成功: modelId={}, supportsImageInput={}, imageCount={}, latencyMs={}",
                        model.getModelId(), model.supportsImageInput(), testImages.size(), System.currentTimeMillis() - start);
            } catch (Exception e) {
                result.setSuccess(false);
                result.setErrorMessage(e.getMessage());
                log.warn("模型探测失败: modelId={}, supportsImageInput={}, imageCount={}, latencyMs={}, message={}",
                        model.getModelId(), model.supportsImageInput(), testImages.size(),
                        System.currentTimeMillis() - start, e.getMessage());
            }
            result.setLatencyMs(System.currentTimeMillis() - start);
            results.add(result);
        }

        return results;
    }

    private List<String> loadProbeImages() {
        Path pictureDir = Paths.get("src", "main", "resources", "picture");
        if (!Files.exists(pictureDir) || !Files.isDirectory(pictureDir)) {
            return List.of();
        }

        try (Stream<Path> stream = Files.list(pictureDir)) {
            return stream
                    .filter(Files::isRegularFile)
                    .sorted(Comparator.comparing(path -> path.getFileName().toString()))
                    .limit(2)
                    .map(this::readImageAsBase64)
                    .toList();
        } catch (IOException e) {
            throw new BusinessException("读取测试图片失败: " + e.getMessage());
        }
    }

    private String readImageAsBase64(Path path) {
        try {
            byte[] bytes = Files.readAllBytes(path);
            return aiClient.imageFileToBase64(bytes);
        } catch (IOException e) {
            throw new BusinessException("读取测试图片失败: " + path.getFileName());
        }
    }

    private String buildPreview(String response) {
        if (response == null || response.isBlank()) {
            return "";
        }
        return response.length() > 200 ? response.substring(0, 200) + "..." : response;
    }

    private void clearActiveModelsCache() {
        cacheService.invalidateActiveModels();
    }

    @Override
    public int getTotalBattles() {
        return Math.toIntExact(battleMapper.selectCount(null));
    }

    @Override
    public int getTotalUsers() {
        return Math.toIntExact(userMapper.selectCount(null));
    }

    @Override
    public String exportPreferenceJson() {
        List<Battle> battles = battleMapper.selectList(null);
        List<Map<String, Object>> data = new ArrayList<>();
        for (Battle battle : battles) {
            Map<String, Object> item = new HashMap<>();
            item.put("battleId", battle.getId());
            item.put("modelA", battle.getModelAId());
            item.put("modelB", battle.getModelBId());
            item.put("result", battle.getWinner());
            item.put("createdAt", battle.getCreatedAt());
            data.add(item);
        }
        return JSONUtil.toJsonPrettyStr(data);
    }

    @Override
    public String exportPreferenceJsonl() {
        List<Battle> battles = battleMapper.selectList(null);
        StringBuilder sb = new StringBuilder();
        for (Battle battle : battles) {
            Map<String, Object> item = new HashMap<>();
            item.put("battleId", battle.getId());
            item.put("modelA", battle.getModelAId());
            item.put("modelB", battle.getModelBId());
            item.put("result", battle.getWinner());
            item.put("createdAt", battle.getCreatedAt());
            sb.append(JSONUtil.toJsonStr(item)).append("\n");
        }
        return sb.toString();
    }
}
