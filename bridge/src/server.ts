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
          <div style="text-align:center; font-family:sans-serif; margin-top:50px;">
            <h2>🐈 Nanobot WhatsApp Bridge</h2>
            <p>Aguardando QR Code... Por favor, aguarde alguns segundos.</p>
            <p style="color:gray;">Se o status do WhatsApp estiver como "conectado", feche esta aba.</p>
            <script>setTimeout(() => location.reload(), 3000);</script>
          </div>
        `;
      } else {
        body = `
          <div style="text-align:center; font-family:sans-serif; margin-top:30px;">
            <h2>🐈 Escaneie para Conectar</h2>
            <p>Abra seu WhatsApp > Configurações > Aparelhos Conectados > Conectar um aparelho</p>
            <div style="display:inline-block; background:white; padding:20px; border:1px solid #ccc; margin:20px 0;">
              <pre style="font-family:monospace; line-height:1; font-size:10px; background:white; color:black;">${this.currentQR}</pre>
            </div>
            <p>O QR Code será atualizado automaticamente se expirar.</p>
            <script>setTimeout(() => location.reload(), 5000);</script>
          </div>
        `;
      }
      
      res.end(`<html><head><title>Nanobot - WhatsApp Login</title></head><body style="background:#f0f2f5;">${body}</body></html>`);
    });

    httpServer.listen(webPort, '0.0.0.0', () => {
      console.log(`🌐 Web interface for QR Code: http://localhost:${webPort}`);
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
