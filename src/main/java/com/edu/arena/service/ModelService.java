package com.edu.arena.service;

import com.edu.arena.dto.request.AddModelRequest;
import com.edu.arena.dto.response.ModelProbeResultVO;
import com.edu.arena.entity.Model;

import java.util.List;

/**
 * Model Service Interface
 */
public interface ModelService {

    /**
     * Get all models
     */
    List<Model> getAllModels();

    /**
     * Add model
     */
    void addModel(AddModelRequest request);

    /**
     * Toggle model status
     */
    void toggleModelStatus(Long modelId);

    /**
     * Get active models
     */
    List<Model> getActiveModels();

    /**
     * 批量探测模型可用性
     */
    List<ModelProbeResultVO> probeAllModels();

    /**
     * Get total battles count
     */
    int getTotalBattles();

    /**
     * Get total users count
     */
    int getTotalUsers();

    /**
     * Export preference data as JSON
     */
    String exportPreferenceJson();

    /**
     * Export preference data as JSONL
     */
    String exportPreferenceJsonl();

}
