package com.edu.arena.service;

import com.edu.arena.dto.request.ExportQuery;

import java.io.IOException;
import java.io.OutputStream;

/**
 * 偏好数据集导出服务。
 *
 * <p>导出形态固定为 ZIP 包：
 * <pre>
 * preference_export_yyyyMMdd_HHmmss.zip
 * ├── manifest.json   导出元信息（导出时间、过滤条件、总条数、图片总数、schema_version）
 * ├── data.jsonl      每行一条 battle 完整数据（schema 详见 ExportItem）
 * └── images/
 *     └── task_{taskId}/01.jpg, 02.jpg, ...   作文图片，按 task 去重写入
 * </pre>
 *
 * 仅导出 status=voted 的对战，脏数据（generating/ready/failed）一律不导出。</p>
 */
public interface ExportService {

    /**
     * 流式写出 ZIP 包到给定输出流。
     *
     * @param query 过滤参数（可空字段使用默认）
     * @param out   响应输出流，由调用方负责关闭
     */
    void exportZip(ExportQuery query, OutputStream out) throws IOException;
}
