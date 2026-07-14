#!/bin/bash
echo "=== 测试所有 /dev/video* 设备 ==="
echo

for dev in 0 1 2 3 4 6 7 8; do
    echo -n "/dev/video$dev: "
    
    # 先用 v4l2-ctl 测试是否能打开
    if v4l2-ctl -d /dev/video$dev --all 2>/dev/null | grep -q "Driver"; then
        echo "✅ v4l2-ctl 可访问"
        
        # 测试是否能捕获
        if v4l2-ctl -d /dev/video$dev --set-fmt-video=width=640,height=480,pixelformat=MJPG --stream-mmap --stream-count=3 2>/dev/null | grep -q "<<<<<"; then
            echo "   ✅ 可以捕获帧 (MJPG)"
        elif v4l2-ctl -d /dev/video$dev --set-fmt-video=width=640,height=480,pixelformat=YUYV --stream-mmap --stream-count=3 2>/dev/null | grep -q "<<<<<"; then
            echo "   ✅ 可以捕获帧 (YUYV)"
        else
            echo "   ⚠️ 可打开但无法捕获帧"
        fi
    else
        echo "❌ 无法打开 (可能不是摄像头或已被占用)"
    fi
done

echo
echo "=== 完成 ==="
