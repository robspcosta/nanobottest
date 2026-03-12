/**
 * WhatsApp client wrapper using Baileys.
 * Based on OpenClaw's working implementation.
 */

/* eslint-disable @typescript-eslint/no-explicit-any */
import makeWASocket, {
  DisconnectReason,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
  downloadContentFromMessage,
  downloadMediaMessage,
} from '@whiskeysockets/baileys';

import { Boom } from '@hapi/boom';
import qrcode from 'qrcode-terminal';
import pino from 'pino';
import { Buffer } from 'node:buffer';

const VERSION = '0.1.0';

export interface InboundMessage {
  id: string;
  sender: string;
  pn: string;
  content: string;
  timestamp: number;
  isGroup: boolean;
  media?: {
    type: 'audio' | 'image' | 'document';
    data: string; // base64
    mimetype: string;
  };
}

export interface WhatsAppClientOptions {
  authDir: string;
  onMessage: (msg: InboundMessage) => void;
  onQR: (qr: string) => void;
  onStatus: (status: string) => void;
}

export class WhatsAppClient {
  private sock: any = null;
  private options: WhatsAppClientOptions;
  private reconnecting = false;

  constructor(options: WhatsAppClientOptions) {
    this.options = options;
  }

  async connect(): Promise<void> {
    const logger = pino({ level: 'silent' });
    const { state, saveCreds } = await useMultiFileAuthState(this.options.authDir);
    const { version } = await fetchLatestBaileysVersion();

    console.log(`Using Baileys version: ${version.join('.')}`);

    // Create socket following OpenClaw's pattern
    this.sock = makeWASocket({
      auth: {
        creds: state.creds,
        keys: makeCacheableSignalKeyStore(state.keys, logger),
      },
      version,
      logger,
      printQRInTerminal: false,
      browser: ['nanobot', 'cli', VERSION],
      syncFullHistory: false,
      markOnlineOnConnect: false,
    });

    // Handle WebSocket errors
    if (this.sock.ws && typeof this.sock.ws.on === 'function') {
      this.sock.ws.on('error', (err: Error) => {
        console.error('WebSocket error:', err.message);
      });
    }

    // Handle connection updates
    this.sock.ev.on('connection.update', async (update: any) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        // Display QR code in terminal
        console.log('\n📱 Scan this QR code with WhatsApp (Linked Devices):\n');
        qrcode.generate(qr, { small: true });
        this.options.onQR(qr);
      }

      if (connection === 'close') {
        const statusCode = (lastDisconnect?.error as Boom)?.output?.statusCode;
        const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

        console.log(`Connection closed. Status: ${statusCode}, Will reconnect: ${shouldReconnect}`);
        this.options.onStatus('disconnected');

        // If 401 (Unauthorized), the session is dead. Clear auth dir to force new QR.
        if (statusCode === DisconnectReason.loggedOut || statusCode === 401) {
          console.log('❌ Session expired or unauthorized. Clearing authentication data...');
          try {
            import('fs').then(fs => {
              if (fs.existsSync(this.options.authDir)) {
                fs.rmSync(this.options.authDir, { recursive: true, force: true });
                console.log('✅ Auth data cleared. Please restart to scan new QR code.');
              }
            });
          } catch (e) {
            console.error('Failed to clear auth dir:', e);
          }
        }

        if (shouldReconnect && !this.reconnecting) {
          this.reconnecting = true;
          console.log('Reconnecting in 5 seconds...');
          setTimeout(() => {
            this.reconnecting = false;
            this.connect();
          }, 5000);
        }
      } else if (connection === 'open') {
        console.log('✅ Connected to WhatsApp');
        this.options.onStatus('connected');
      }
    });

    // Save credentials on update
    this.sock.ev.on('creds.update', saveCreds);

    // Handle incoming messages
    this.sock.ev.on('messages.upsert', async ({ messages, type }: { messages: any[]; type: string }) => {
      if (type !== 'notify') return;

      for (const msg of messages) {
        // Skip own messages
        if (msg.key.fromMe) continue;

        // Skip status updates
        if (msg.key.remoteJid === 'status@broadcast') continue;

        const isGroup = msg.key.remoteJid?.endsWith('@g.us') || false;

        // Root message object
        const message = msg.message;

        // Log ALL top-level keys of the message for debugging
        console.log(`🔍 [Bridge] Message keys: ${message ? Object.keys(message).join(', ') : 'null'}`);

        const mediaFound = this.getMedia(message);
        console.log(`🔍 [Bridge] getMedia result: ${mediaFound ? mediaFound.type : 'null'}`);

        // 1. Determine Content
        let content = '';
        if (message?.conversation) content = message.conversation;
        else if (message?.extendedTextMessage?.text) content = message.extendedTextMessage.text;
        else if (mediaFound?.obj?.caption) content = mediaFound.obj.caption;

        if (!content && mediaFound?.type === 'audio') {
          content = '[Voice Message]';
        }

        // 2. Handle Media Download
        let mediaData: any = undefined;
        if (mediaFound) {
          console.log(`📥 [Bridge] Starting download of ${mediaFound.type}...`);

          try {
            // Wrap download in a timeout to prevent hanging
            const downloadPromise = downloadMediaMessage(
              msg,
              'buffer',
              {},
              {
                logger: pino({ level: 'silent' }),
                reuploadRequest: this.sock?.updateMediaMessage
              }
            );

            const timeoutPromise = new Promise<null>((_, reject) =>
              setTimeout(() => reject(new Error('Download timed out after 15s')), 15000)
            );

            const buffer = await Promise.race([downloadPromise, timeoutPromise]) as Buffer | null;

            if (buffer && buffer.length > 0) {
              console.log(`✅ [Bridge] Download successful: ${buffer.length} bytes`);
              mediaData = {
                type: mediaFound.type,
                data: buffer.toString('base64'),
                mimetype: mediaFound.obj.mimetype || (mediaFound.type === 'audio' ? 'audio/ogg' : 'image/jpeg')
              };
            } else {
              console.warn(`⚠️ [Bridge] Download returned empty/null buffer`);
            }
          } catch (e: any) {
            console.error(`❌ [Bridge] downloadMediaMessage failed: ${e.message}`);

            // Fallback: try downloadContentFromMessage
            console.log(`🔄 [Bridge] Trying fallback download method...`);
            try {
              const stream = await downloadContentFromMessage(mediaFound.obj, mediaFound.type);
              const chunks: Uint8Array[] = [];
              for await (const chunk of stream) {
                chunks.push(chunk);
              }
              const fallbackBuffer = Buffer.concat(chunks);
              if (fallbackBuffer.length > 0) {
                console.log(`✅ [Bridge] Fallback download successful: ${fallbackBuffer.length} bytes`);
                mediaData = {
                  type: mediaFound.type,
                  data: fallbackBuffer.toString('base64'),
                  mimetype: mediaFound.obj.mimetype || (mediaFound.type === 'audio' ? 'audio/ogg' : 'image/jpeg')
                };
              } else {
                console.warn(`⚠️ [Bridge] Fallback also returned empty buffer`);
              }
            } catch (e2: any) {
              console.error(`❌ [Bridge] Fallback download also failed: ${e2.message}`);
            }
          }
        }

        console.log(`📤 [Bridge] Sending to Python: content="${content.substring(0, 50)}", hasMedia=${!!mediaData}`);

        this.options.onMessage({
          id: msg.key.id || '',
          sender: msg.key.remoteJid || '',
          pn: msg.key.remoteJidAlt || '',
          content: content,
          timestamp: msg.messageTimestamp as number,
          isGroup,
          media: mediaData,
        });
      }
    });
  }

  private getMedia(message: any): { type: 'audio' | 'image' | 'video' | 'document'; obj: any } | null {
    if (!message) return null;
    if (message.audioMessage) return { type: 'audio', obj: message.audioMessage };
    if (message.imageMessage) return { type: 'image', obj: message.imageMessage };
    if (message.videoMessage) return { type: 'video', obj: message.videoMessage };
    if (message.documentMessage) return { type: 'document', obj: message.documentMessage };

    // Handle nested messages (view once, ephemeral, etc)
    const nested =
      message.viewOnceMessage?.message ||
      message.viewOnceMessageV2?.message ||
      message.viewOnceMessageV2Extension?.message ||
      message.ephemeralMessage?.message ||
      message.documentWithCaptionMessage?.message ||
      message.editMessage?.message ||
      message.templateMessage?.hydratedTemplate?.message ||
      message.templateMessage?.hydratedDraftTemplate?.message ||
      message.interactiveMessage?.body?.message;

    if (nested) return this.getMedia(nested);
    return null;
  }

  async sendMessage(to: string, text: string): Promise<void> {
    if (!this.sock) {
      throw new Error('Not connected');
    }

    await this.sock.sendMessage(to, { text });
  }

  async disconnect(): Promise<void> {
    if (this.sock) {
      this.sock.end(undefined);
      this.sock = null;
    }
  }
}
