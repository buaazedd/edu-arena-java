package com.edu.arena.common.utils;

import lombok.extern.slf4j.Slf4j;
import net.coobird.thumbnailator.Thumbnails;

import javax.imageio.IIOImage;
import javax.imageio.ImageIO;
import javax.imageio.ImageWriteParam;
import javax.imageio.ImageWriter;
import javax.imageio.stream.ImageOutputStream;
import java.awt.*;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.Base64;
import java.util.Iterator;

/**
 * 图片压缩工具
 */
@Slf4j
public final class ImageCompressUtils {

    private static final int MAX_EDGE = 1600;
    private static final int MIN_EDGE = 1024;
    private static final float JPEG_QUALITY = 0.72f;
    private static final long MAX_BASE64_IMAGE_BYTES = 1_000_000L;

    private ImageCompressUtils() {
    }

    public static String compressBase64Image(String base64) {
        if (base64 == null || base64.isBlank()) {
            return base64;
        }

        byte[] inputBytes = decodeBase64(base64);
        byte[] compressedBytes = compressBytes(inputBytes);
        return Base64.getEncoder().encodeToString(compressedBytes);
    }

    public static byte[] compressBytes(byte[] inputBytes) {
        if (inputBytes == null || inputBytes.length == 0) {
            return inputBytes;
        }

        long before = inputBytes.length;
        try {
            BufferedImage src = ImageIO.read(new ByteArrayInputStream(inputBytes));
            if (src == null) {
                log.warn("图片压缩失败，无法识别图片格式，回退原图: size={} bytes", before);
                return inputBytes;
            }

            int maxSide = Math.max(src.getWidth(), src.getHeight());
            if (before <= MAX_BASE64_IMAGE_BYTES && maxSide <= MIN_EDGE) {
                log.debug("图片无需压缩: size={} bytes, maxSide={} <= {}", before, maxSide, MIN_EDGE);
                return inputBytes;
            }

            byte[] compressed = tryCompress(src, before, MAX_EDGE, JPEG_QUALITY);
            if (compressed.length >= before) {
                // 再尝试更激进的压缩，尽量保证体积确实下降
                byte[] aggressive = tryCompress(src, before, MIN_EDGE, 0.58f);
                if (aggressive.length < compressed.length) {
                    compressed = aggressive;
                }
            }

            if (compressed.length >= before) {
                log.warn("压缩后体积未下降，回退原图: before={} bytes, after={} bytes", before, compressed.length);
                return inputBytes;
            }

            log.info("图片压缩完成: before={} bytes, after={} bytes, ratio={}%, maxSide={}, quality≈{}",
                    before, compressed.length, String.format("%.1f", compressed.length * 100.0 / before), maxSide, JPEG_QUALITY);
            return compressed;
        } catch (Exception ex) {
            log.warn("图片压缩异常，回退原图: size={} bytes, err={}", before, ex.getMessage(), ex);
            return inputBytes;
        }
    }

    private static byte[] tryCompress(BufferedImage src, long beforeBytes, int maxEdge, float quality) throws IOException {
        BufferedImage processed = resizeIfNeeded(src, maxEdge);
        byte[] compressed = encodeJpeg(processed, quality);
        log.debug("图片压缩尝试: before={} bytes, after={} bytes, maxEdge={}, quality={}", beforeBytes, compressed.length, maxEdge, quality);
        return compressed;
    }

    private static BufferedImage resizeIfNeeded(BufferedImage src, int maxEdge) throws IOException {
        int width = src.getWidth();
        int height = src.getHeight();
        int max = Math.max(width, height);
        if (max <= maxEdge) {
            return toRgbImage(src);
        }

        double scale = (double) maxEdge / max;
        int targetWidth = Math.max(1, (int) Math.round(width * scale));
        int targetHeight = Math.max(1, (int) Math.round(height * scale));

        BufferedImage resized = Thumbnails.of(src)
                .scale(scale)
                .asBufferedImage();
        return toRgbImage(resized, targetWidth, targetHeight);
    }

    private static BufferedImage toRgbImage(BufferedImage src) {
        return toRgbImage(src, src.getWidth(), src.getHeight());
    }

    private static BufferedImage toRgbImage(BufferedImage src, int width, int height) {
        BufferedImage rgb = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
        Graphics2D g = rgb.createGraphics();
        try {
            g.setColor(Color.WHITE);
            g.fillRect(0, 0, width, height);
            g.drawImage(src, 0, 0, width, height, null);
        } finally {
            g.dispose();
        }
        return rgb;
    }

    private static byte[] encodeJpeg(BufferedImage image, float quality) throws IOException {
        ByteArrayOutputStream baos = new ByteArrayOutputStream();
        Iterator<ImageWriter> writers = ImageIO.getImageWritersByFormatName("jpg");
        if (!writers.hasNext()) {
            ImageIO.write(image, "jpg", baos);
            return baos.toByteArray();
        }

        ImageWriter writer = writers.next();
        try (ImageOutputStream ios = ImageIO.createImageOutputStream(baos)) {
            writer.setOutput(ios);
            ImageWriteParam param = writer.getDefaultWriteParam();
            if (param.canWriteCompressed()) {
                param.setCompressionMode(ImageWriteParam.MODE_EXPLICIT);
                param.setCompressionQuality(quality);
            }
            writer.write(null, new IIOImage(image, null, null), param);
        } finally {
            writer.dispose();
        }
        return baos.toByteArray();
    }

    private static byte[] decodeBase64(String base64) {
        String cleaned = base64.trim();
        int commaIndex = cleaned.indexOf(',');
        if (commaIndex >= 0 && cleaned.startsWith("data:")) {
            cleaned = cleaned.substring(commaIndex + 1);
        }
        return Base64.getDecoder().decode(cleaned);
    }
}
