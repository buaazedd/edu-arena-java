package com.edu.arena.common.utils;

import org.junit.jupiter.api.Test;

import javax.imageio.ImageIO;
import java.awt.*;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.util.Base64;

import static org.junit.jupiter.api.Assertions.*;

public class ImageCompressUtilsTest {

    @Test
    void shouldCompressLargeBase64Image() throws Exception {
        String base64 = buildLargeTestImageBase64(3000, 2200);

        byte[] originalBytes = Base64.getDecoder().decode(base64);
        String compressedBase64 = ImageCompressUtils.compressBase64Image(base64);
        byte[] compressedBytes = Base64.getDecoder().decode(compressedBase64);

        assertNotNull(compressedBase64);
        assertTrue(compressedBytes.length > 0);
        assertTrue(compressedBytes.length <= originalBytes.length, "compressed bytes should not be larger than original");
    }

    @Test
    void shouldReturnOriginalWhenInputBlank() {
        assertNull(ImageCompressUtils.compressBase64Image(null));
        assertEquals("", ImageCompressUtils.compressBase64Image(""));
    }

    @Test
    void shouldNotFailForInvalidBase64() {
        assertThrows(IllegalArgumentException.class, () -> ImageCompressUtils.compressBase64Image("not-a-valid-base64"));
    }

    @Test
    void shouldReturnOriginalBytesWhenAlreadySmall() throws Exception {
        String base64 = buildLargeTestImageBase64(200, 200);
        byte[] originalBytes = Base64.getDecoder().decode(base64);
        byte[] compressedBytes = ImageCompressUtils.compressBytes(originalBytes);
        assertArrayEquals(originalBytes, compressedBytes);
    }

    @Test
    void shouldCompressPngImageAndKeepValidOutput() throws Exception {
        String base64 = buildLargeTestImageBase64(2800, 2000);
        byte[] originalBytes = Base64.getDecoder().decode(base64);
        byte[] compressedBytes = ImageCompressUtils.compressBytes(originalBytes);

        assertNotNull(compressedBytes);
        assertTrue(compressedBytes.length > 0);
        assertTrue(compressedBytes.length < originalBytes.length, "png image should be compressed smaller");

        BufferedImage decoded = ImageIO.read(new java.io.ByteArrayInputStream(compressedBytes));
        assertNotNull(decoded, "compressed bytes should still be a readable image");
        assertTrue(Math.max(decoded.getWidth(), decoded.getHeight()) <= 1600, "compressed image should respect max edge");
    }

    private static String buildLargeTestImageBase64(int width, int height) throws Exception {
        BufferedImage image = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
        Graphics2D g = image.createGraphics();
        try {
            g.setColor(Color.WHITE);
            g.fillRect(0, 0, width, height);
            g.setColor(Color.BLACK);
            g.setFont(new Font("SansSerif", Font.BOLD, 80));
            for (int i = 0; i < 30; i++) {
                g.drawString("作文测试图片 " + i, 100, 120 + i * 60);
            }
        } finally {
            g.dispose();
        }

        ByteArrayOutputStream baos = new ByteArrayOutputStream();
        ImageIO.write(image, "png", baos);
        return Base64.getEncoder().encodeToString(baos.toByteArray());
    }
}
