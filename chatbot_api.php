<?php
header("Content-Type: application/json");
header("Access-Control-Allow-Origin: *"); // Cho phép truy cập từ mọi nguồn
header("Access-Control-Allow-Methods: POST, GET, OPTIONS");
header("Access-Control-Allow-Headers: Content-Type, Authorization");

// Xử lý OPTIONS request cho CORS preflight
if ($_SERVER['REQUEST_METHOD'] == 'OPTIONS') {
    exit(0);
}

// Cấu hình kết nối
$python_host = 'localhost'; // Điều chỉnh nếu cần
$python_port = '5001';      // Điều chỉnh nếu cần
$python_service_url = "http://{$python_host}:{$python_port}/chat";
$python_reset_url = "http://{$python_host}:{$python_port}/reset";

// Timeout cho kết nối (tăng lên để tránh lỗi timeout)
$timeout = 30; // 30 giây

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $input = json_decode(file_get_contents('php://input'), true);
    
    if (isset($input['action']) && $input['action'] === 'reset') {
        // Gọi endpoint reset của Python service
        $options = [
            'http' => [
                'header'  => "Content-type: application/json\r\n",
                'method'  => 'POST',
                'content' => json_encode([]), // Reset không cần payload
                'ignore_errors' => true, // Để bắt lỗi từ Python service
                'timeout' => $timeout // Thêm timeout
            ]
        ];
        $context = stream_context_create($options);
        
        try {
            $result = @file_get_contents($python_reset_url, false, $context);
            
            if ($result === FALSE) {
                // Kiểm tra lỗi kết nối
                $error = error_get_last();
                http_response_code(503); // Service Unavailable
                echo json_encode([
                    'error' => 'Không thể kết nối đến dịch vụ AI', 
                    'detail' => $error['message'] ?? 'Không thể truy cập dịch vụ AI. Vui lòng kiểm tra xem Python service có đang chạy không.'
                ]);
                exit;
            }
            
            // Kiểm tra HTTP status code
            if (isset($http_response_header[0])) {
                $status_line = $http_response_header[0];
                preg_match('{HTTP\/\S*\s(\d{3})}', $status_line, $match);
                $status_code = $match[1] ?? 500;
                
                if ($status_code >= 200 && $status_code < 300) {
                    echo $result; // Trả về phản hồi JSON từ Python
                } else {
                    http_response_code($status_code);
                    $error_detail = json_decode($result, true);
                    echo json_encode([
                        'error' => 'Lỗi khi reset chat',
                        'detail' => $error_detail['error'] ?? $error_detail['detail'] ?? $status_code
                    ]);
                }
            } else {
                http_response_code(500);
                echo json_encode(['error' => 'Phản hồi không hợp lệ từ Python service']);
            }
        } catch (Exception $e) {
            http_response_code(500);
            echo json_encode(['error' => 'Lỗi khi xử lý yêu cầu reset', 'detail' => $e->getMessage()]);
        }
        exit;
    }

    if (isset($input['message'])) {
        $user_message = $input['message'];
        
        if (empty(trim($user_message))) {
            http_response_code(400);
            echo json_encode(['error' => 'Tin nhắn không được để trống.']);
            exit;
        }

        $data = ['message' => $user_message];
        $options = [
            'http' => [
                'header'  => "Content-Type: application/json\r\n",
                'method'  => 'POST',
                'content' => json_encode($data),
                'ignore_errors' => true, // Để bắt lỗi từ Python service
                'timeout' => $timeout // Thêm timeout cho xử lý AI có thể lâu
            ],
        ];
        $context = stream_context_create($options);
        
        try {
            $result = @file_get_contents($python_service_url, false, $context);
            
            if ($result === FALSE) {
                // Kiểm tra lỗi kết nối
                $error = error_get_last();
                http_response_code(503); // Service Unavailable
                echo json_encode([
                    'error' => 'Không thể kết nối đến dịch vụ AI',
                    'detail' => $error['message'] ?? 'Không thể truy cập dịch vụ AI. Vui lòng kiểm tra xem Python service có đang chạy không.'
                ]);
                exit;
            }
            
            // Kiểm tra HTTP status code
            if (isset($http_response_header[0])) {
                $status_line = $http_response_header[0];
                preg_match('{HTTP\/\S*\s(\d{3})}', $status_line, $match);
                $status_code = $match[1] ?? 500;
                
                if ($status_code >= 200 && $status_code < 300) {
                    // Trả về phản hồi JSON từ Python service cho frontend
                    echo $result;
                } else {
                    http_response_code($status_code);
                    $error_detail = json_decode($result, true);
                    echo json_encode([
                        'error' => 'Lỗi từ dịch vụ AI',
                        'detail' => $error_detail['error'] ?? $error_detail['detail'] ?? "HTTP Error: $status_code"
                    ]);
                }
            } else {
                http_response_code(500);
                echo json_encode(['error' => 'Phản hồi không hợp lệ từ Python service']);
            }
        } catch (Exception $e) {
            http_response_code(500);
            echo json_encode(['error' => 'Lỗi khi xử lý yêu cầu', 'detail' => $e->getMessage()]);
        }
    } else {
        http_response_code(400);
        echo json_encode(['error' => 'Tin nhắn không hợp lệ.']);
    }
} else {
    http_response_code(405); // Method Not Allowed
    echo json_encode(['error' => 'Phương thức không được hỗ trợ. Chỉ chấp nhận POST.']);
}
?>