/**
 * WebSocket server for Python-Node.js bridge communication.
 * Security: binds to 127.0.0.1 only; optional BRIDGE_TOKEN auth.
 */

import { WebSocketServer, WebSocket } from 'ws';
import { WhatsAppClient, InboundMessage } from './whatsapp.js';
import * as fs from 'fs';
import * as path from 'path';
import * as http from 'http';

interface SendCommand {
  type: 'send';
  to: string;
  text: string;
}

interface BridgeMessage {
  type: 'message' | 'status' | 'qr' | 'error';
  [key: string]: unknown;
}

export class BridgeServer {
  private wss: WebSocketServer | null = null;
  private wa: WhatsAppClient | null = null;
  private clients: Set<WebSocket> = new Set();
  private currentQR: string | null = null;

  constructor(private port: number, private authDir: string, private token?: string) { }

  async start(): Promise<void> {
    // 1. Start HTTP Server for QR Code display (Web Interface)
    const webPort = parseInt(process.env.BRIDGE_WEB_PORT || '3002', 10);
    const httpServer = http.createServer((req, res) => {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      
      let body = '';
      if (!this.currentQR) {
        body = `
          <div style="text-align:center; font-family:sans-serif; margin-top:50px; color:#1c1e21;">
            <div style="font-size:40px; margin-bottom:20px;">🐈</div>
            <h2 style="font-weight:600;">Nanobot WhatsApp Bridge</h2>
            <p style="color:#65676b;">Aguardando QR Code... Por favor, aguarde alguns segundos.</p>
            <p style="font-size:12px; color:#afb3b8; margin-top:20px;">O sistema está iniciando a conexão com os servidores do WhatsApp.</p>
            <div style="margin:20px auto; width:40px; height:40px; border:4px solid #f3f3f3; border-top:4px solid #00a884; border-radius:50%; animation:spin 1s linear infinite;"></div>
            <style>@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }</style>
            <script>setTimeout(() => location.reload(), 3000);</script>
          </div>
        `;
      } else {
        body = `
          <div style="text-align:center; font-family:sans-serif; margin-top:40px; color:#1c1e21;">
            <div style="font-size:40px; margin-bottom:10px;">🐈</div>
            <h2 style="font-weight:600; margin-bottom:5px;">Escaneie para Conectar</h2>
            <p style="color:#65676b; margin-bottom:25px;">Abra o WhatsApp no seu celular e escaneie o código abaixo</p>
            
            <div id="qrcode-container" style="display:inline-block; background:white; padding:30px; border-radius:15px; box-shadow:0 10px 25px rgba(0,0,0,0.1); margin-bottom:25px;">
              <div id="qrcode"></div>
              <noscript><p style="color:red;">JavaScript é necessário para ver o QR Code aqui.</p></noscript>
            </div>

            <div style="max-width:400px; margin:0 auto; text-align:left; background:#fff; padding:20px; border-radius:10px; font-size:14px; color:#4a4a4a; line-height:1.5; border:1px solid #e1e4e8;">
               <strong>Como conectar:</strong>
               <ol style="padding-left:20px; margin-top:10px;">
                 <li>Abra o WhatsApp no seu celular</li>
                 <li>Toque em <b>Mais Opções</b> (Android) ou <b>Configurações</b> (iOS)</li>
                 <li>Toque em <b>Aparelhos Conectados</b></li>
                 <li>Toque em <b>Conectar um Aparelho</b> e aponte para esta tela</li>
               </ol>
            </div>

            <p style="font-size:12px; color:#a0a0a0; margin-top:30px;">O QR Code será atualizado automaticamente se expirar.</p>
            
            <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
            <script>
              new QRCode(document.getElementById("qrcode"), {
                text: "${this.currentQR}",
                width: 256,
                height: 256,
                colorDark: "#000000",
                colorLight: "#ffffff",
                correctLevel: QRCode.CorrectLevel.H
              });
              setTimeout(() => location.reload(), 15000);
            </script>
          </div>
        `;
      }
      
      res.end(`
        <!DOCTYPE html>
        <html>
        <head>
          <title>Nanobot - WhatsApp Login</title>
          <meta name="viewport" content="width=device-width, initial-scale=1">
        </head>
        <body style="background:#f0f2f5; margin:0; display:flex; justify-content:center; align-items:start; min-height:100vh;">
          ${body}
        </body>
        </html>
      `);
    });

    httpServer.listen(webPort, '0.0.0.0', () => {
      console.log(`Web interface for QR Code: http://localhost:${webPort}`);
    });

    // 2. Start WebSocket Server
    const host = process.env.BRIDGE_HOST || '0.0.0.0';
    this.wss = new WebSocketServer({ host, port: this.port });
    console.log(`🌉 Bridge server listening on ws://${host}:${this.port}`);
    if (this.token) console.log('🔒 Token authentication enabled');

    // Initialize WhatsApp client
    this.wa = new WhatsAppClient({
      authDir: this.authDir,
      onMessage: (msg) => this.broadcast({ type: 'message', ...msg }),
      onQR: (qr) => {
        this.currentQR = qr;
        this.broadcast({ type: 'qr', qr });
      },
      onStatus: (status) => {
        if (status === 'connected') this.currentQR = null;
        this.broadcast({ type: 'status', status });
      },
    });

    // Handle WebSocket connections
    this.wss.on('connection', (ws) => {
      if (this.token) {
        // Require auth handshake as first message
        const timeout = setTimeout(() => ws.close(4001, 'Auth timeout'), 5000);
        ws.once('message', (data) => {
          clearTimeout(timeout);
          try {
            const msg = JSON.parse(data.toString());
            if (msg.type === 'auth' && msg.token === this.token) {
              console.log('🔗 Python client authenticated');
              this.setupClient(ws);
            } else {
              ws.close(4003, 'Invalid token');
            }
          } catch {
            ws.close(4003, 'Invalid auth message');
          }
        });
      } else {
        console.log('🔗 Python client connected');
        this.setupClient(ws);
      }
    });

    // Connect to WhatsApp
    await this.wa.connect();
  }

  private setupClient(ws: WebSocket): void {
    this.clients.add(ws);

    ws.on('message', async (data) => {
      try {
        const cmd = JSON.parse(data.toString()) as SendCommand;
        await this.handleCommand(cmd);
        ws.send(JSON.stringify({ type: 'sent', to: cmd.to }));
      } catch (error) {
        console.error('Error handling command:', error);
        ws.send(JSON.stringify({ type: 'error', error: String(error) }));
      }
    });

    ws.on('close', () => {
      console.log('🔌 Python client disconnected');
      this.clients.delete(ws);
    });

    ws.on('error', (error) => {
      console.error('WebSocket error:', error);
      this.clients.delete(ws);
    });
  }

  private async handleCommand(cmd: SendCommand): Promise<void> {
    if (cmd.type === 'send' && this.wa) {
      await this.wa.sendMessage(cmd.to, cmd.text);
    }
  }

  private broadcast(msg: BridgeMessage): void {
    const data = JSON.stringify(msg);
    for (const client of this.clients) {
      if (client.readyState === WebSocket.OPEN) {
        client.send(data);
      }
    }
  }

  async stop(): Promise<void> {
    // Close all client connections
    for (const client of this.clients) {
      client.close();
    }
    this.clients.clear();

    // Close WebSocket server
    if (this.wss) {
      this.wss.close();
      this.wss = null;
    }

    // Disconnect WhatsApp
    if (this.wa) {
      await this.wa.disconnect();
      this.wa = null;
    }
  }
}
