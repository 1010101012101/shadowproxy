import pylru
from ... import gvars
from ...utils import pack_addr, unpack_addr, ViaNamespace
from ..base.udpclient import UDPClient
from ..base.udpserver import UDPServerBase


class SSUDPServer(UDPServerBase):
    proto = "SS(UDP)"

    def __init__(self, cipher, via=None):
        self.cipher = cipher
        self.via = via or ViaNamespace(ClientClass=UDPClient)
        self.removed = None

        def callback(key, value):
            self.removed = (key, value)

        self.via_clients = pylru.lrucache(256, callback)

    async def __call__(self, sock):
        while True:
            data, addr = await sock.recvfrom(gvars.PACKET_SIZE)
            if len(data) <= self.cipher.IV_SIZE:
                continue
            if addr not in self.via_clients:
                via_client = self.via.new()
                self.via_clients[addr] = via_client
                if self.removed is not None:
                    await self.removed[1].close()
                    self.removed = None
            via_client = self.via_clients[addr]

            iv = data[: self.cipher.IV_SIZE]
            decrypt = self.cipher.make_decrypter(iv)
            data = decrypt(data[self.cipher.IV_SIZE :])
            target_addr, payload = unpack_addr(data)
            await via_client.sendto(payload, target_addr)

            async def sendfrom(data, from_addr):
                iv, encrypt = self.cipher.make_encrypter()
                payload = encrypt(pack_addr(target_addr) + data)
                await sock.sendto(iv + payload, addr)

            await via_client.relay(target_addr, sendfrom)

        for via_client in self.via_clients.values():
            await via_client.close()
