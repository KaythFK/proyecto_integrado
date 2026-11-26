<?php
use PHPMailer\PHPMailer\PHPMailer;
use PHPMailer\PHPMailer\Exception;

require __DIR__ . '/PHPMailer/src/Exception.php';
require __DIR__ . '/PHPMailer/src/PHPMailer.php';
require __DIR__ . '/PHPMailer/src/SMTP.php';

// ==========================================
// DATOS QUE ENVÍA DJANGO
// Recuperación de contraseña: destinatario, enlace, minutos
// Correo con contenido armado en Django: destinatario, asunto, html, texto
// ==========================================
$datos = json_decode(file_get_contents('php://stdin'), true);

$con_contenido = !empty($datos['html']);
if (!$datos || empty($datos['destinatario']) || (!$con_contenido && empty($datos['enlace']))) {
    fwrite(STDERR, 'Datos de entrada incompletos.');
    exit(1);
}

$mail = new PHPMailer(true);

try {
    // ==========================================
    // CONFIGURACIÓN SMTP DE GMAIL
    // ==========================================
    $mail->isSMTP();
    $mail->Host       = getenv('SMTP_HOST') ?: 'smtp.gmail.com';
    $mail->SMTPAuth   = true;
    $mail->Username   = getenv('SMTP_USER');
    $mail->Password   = getenv('SMTP_PASSWORD');
    $mail->SMTPSecure = PHPMailer::ENCRYPTION_STARTTLS;
    $mail->Port       = (int) (getenv('SMTP_PORT') ?: 587);

    // ==========================================
    // REMITENTE Y DESTINATARIO
    // ==========================================
    $mail->setFrom(getenv('SMTP_USER'), getenv('SMTP_FROM_NAME') ?: 'Delegaciones Municipales');
    $mail->addAddress($datos['destinatario']);

    $mail->isHTML(true);
    $mail->CharSet = 'UTF-8';

    if ($con_contenido) {
        // ==========================================
        // CORREO ARMADO EN DJANGO (por ejemplo, credenciales de un usuario nuevo)
        // ==========================================
        $mail->Subject = $datos['asunto'] ?? 'Delegaciones Municipales';
        $mail->Body    = $datos['html'];
        $mail->AltBody = $datos['texto'] ?? strip_tags($datos['html']);
    } else {
        // ==========================================
        // RECUPERACIÓN DE CONTRASEÑA
        // ==========================================
        $enlace  = htmlspecialchars($datos['enlace'], ENT_QUOTES, 'UTF-8');
        $minutos = (int) ($datos['minutos'] ?? 60);

        $mail->Subject = 'Recuperación de contraseña';
        $mail->Body = '
        <div style="
            font-family: Arial, Helvetica, sans-serif;
            max-width: 500px;
            margin: 40px auto;
            padding: 30px;
            border: 1px solid #dddddd;
            border-radius: 10px;
            text-align: center;
            background-color: #ffffff;
        ">
            <h2 style="color: #8B1D19;">
                Recuperación de contraseña
            </h2>

            <p style="color: #555555; font-size: 16px;">
                Hemos recibido una solicitud para restablecer tu contraseña.
            </p>

            <p style="margin: 30px 0;">
                <a href="' . $enlace . '" style="
                    background-color: #8B1D19;
                    color: #ffffff;
                    padding: 14px 28px;
                    border-radius: 8px;
                    text-decoration: none;
                    font-weight: bold;
                    font-size: 16px;
                ">
                    Restablecer contraseña
                </a>
            </p>

            <p style="color: #777777; font-size: 14px;">
                Este enlace es de un solo uso y expira en ' . $minutos . ' minutos.
            </p>

            <p style="color: #999999; font-size: 12px; word-break: break-all;">
                Si el botón no funciona, copia este enlace en tu navegador:<br>' . $enlace . '
            </p>

            <p style="color: #999999; font-size: 13px;">
                Si tú no solicitaste este cambio, puedes ignorar este correo.
            </p>
        </div>
        ';
        $mail->AltBody = 'Para restablecer tu contraseña ingresa a: ' . $datos['enlace'];
    }

    // ==========================================
    // ENVIAR CORREO
    // ==========================================
    $mail->send();
    echo 'OK';
    exit(0);
} catch (Exception $e) {
    fwrite(STDERR, 'Error al enviar el correo: ' . $mail->ErrorInfo);
    exit(1);
}
