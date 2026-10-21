using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Tilemaps;

namespace InfiniteStories
{
    public sealed class TileWorld : MonoBehaviour
    {
        readonly List<Object> assets = new List<Object>();
        readonly List<CityCharacter> residents = new List<CityCharacter>();
        Camera worldCamera;GameObject area; VenueFurniture furniture;TextMesh interactionHint;WorldObject[] points;
        public PlayerMotor Player { get; private set; }
        public string LocationId { get; private set; }
        public PlayerMotor AvatarPrefab { get; set; }
        public void Show(Location location, float x, float y)
        {
            location.Validate();
            if (LocationId != location.id)
            {
                Clear(); LocationId = location.id;points=location.objects;
                area = new GameObject(location.name); area.transform.SetParent(transform);
                var grid = area.AddComponent<Grid>(); grid.cellSize = Vector3.one;
                Tilemap floor = Layer("Paving", 0, false), walls = Layer("Stone", 1, true);
                Tile[] paving = { MakeTile(36,new Color(.20f,.28f,.42f)), MakeTile(36,new Color(.205f,.285f,.425f)), MakeTile(36,new Color(.195f,.275f,.415f)) };
                Tile stone = MakeTile(125,new Color(.35f,.4f,.57f)), water = MakeTile(171,new Color(.3f,.5f,.65f));
                Color roomColor=location.id=="market"?new Color(.28f,.17f,.27f):location.id=="archive"?new Color(.17f,.30f,.31f):new Color(.32f,.24f,.22f);
                Tile room=MakeTile(109,roomColor);
                Tile road=MakeTile(468,new Color(.30f,.40f,.56f)),crossing=MakeTile(435,new Color(.45f,.52f,.61f));
                Tile line=MakeTile(433,new Color(.50f,.57f,.67f)),upperCurb=MakeTile(406,new Color(.40f,.48f,.60f)),lowerCurb=MakeTile(460,new Color(.40f,.48f,.60f));
                for (int iy = 0; iy < location.height; iy++) for (int ix = 0; ix < location.width; ix++)
                {
                    Vector3Int cell = new Vector3Int(ix, iy, 0);
                    bool lane=iy>=4&&iy<=6;
                    bool venue=ix>=5&&ix<=26&&iy>=8&&iy<=15;
                    floor.SetTile(cell, lane ? (ix>=22&&ix<=24 ? crossing:iy==6?upperCurb:iy==4?lowerCurb:ix%4==0?line:road) : venue ? room : paving[(ix * 17 + iy * 13) % 3]);
                    char value = location.rows[iy][ix]; if (value != '0') walls.SetTile(cell, value == '2' ? water : stone);
                }
                DressVenue(location);
                int resident=1;
                foreach (WorldObject obj in location.objects)
                {
                    var marker = new GameObject(obj.id); marker.transform.SetParent(area.transform);
                    marker.transform.position = new Vector3(obj.x, obj.y, 0);
                    var renderer = marker.AddComponent<SpriteRenderer>(); renderer.sortingOrder = 400-Mathf.RoundToInt(obj.y*10);
                    if(obj.kind=="npc" || obj.kind=="gate") {
                        int actor=obj.kind=="gate"?5:location.id=="market"?2:location.id=="archive"?3:resident;
                        var character=marker.AddComponent<CityCharacter>(); character.Actor=actor; character.Pose(Vector2.zero,false);residents.Add(character);
                        if(obj.kind=="gate") renderer.color=new Color(.62f,.85f,.9f);
                        Shadow(obj.x,obj.y);
                    } else renderer.sprite = NightArt.Tile(obj.kind=="portal"?417:obj.id=="tram"?410:281);
                    if (obj.kind == "portal") { marker.transform.localScale = new Vector3(1.2f,1.8f,1); Glow(obj.x,obj.y,new Color(.3f,.8f,.78f,.12f),2.6f); }
                    bool screening=obj.id.StartsWith("screening_note_",System.StringComparison.Ordinal), memory=obj.id.StartsWith("cultural_echo_",System.StringComparison.Ordinal);
                    if(screening||memory){marker.transform.localScale=Vector3.one*.70f;renderer.sortingOrder=3;Glow(obj.x,obj.y,new Color(.94f,.72f,.37f,.16f),1.8f);}
                    var label = new GameObject("Label").AddComponent<TextMesh>(); label.transform.SetParent(marker.transform);
                    label.transform.localPosition = new Vector3(0, 1.65f, 0); label.text = obj.kind=="gate" ? "CURATOR · LAST GATE" : screening ? "SCREENING NOTE "+(int.Parse(obj.id.Substring("screening_note_".Length))+1) : memory ? "MEMORY CARD "+(int.Parse(obj.id.Substring("cultural_echo_".Length))+1) : obj.name;
                    label.characterSize = .08f; label.fontSize = 48; label.anchor = TextAnchor.MiddleCenter;
                    label.color = new Color(.89f,.9f,.85f); label.GetComponent<MeshRenderer>().sortingOrder = 600;
                }
                if (AvatarPrefab != null) Player = Instantiate(AvatarPrefab, area.transform);
                else { var playerObject = new GameObject("Traveler"); playerObject.transform.SetParent(area.transform); Player = playerObject.AddComponent<PlayerMotor>(); }
                interactionHint=new GameObject("Nearby interaction").AddComponent<TextMesh>();interactionHint.transform.SetParent(area.transform);interactionHint.fontSize=48;interactionHint.characterSize=.065f;interactionHint.anchor=TextAnchor.MiddleCenter;interactionHint.color=new Color(.94f,.72f,.37f);interactionHint.GetComponent<MeshRenderer>().sortingOrder=620;
                Camera camera = Camera.main;
                if (camera == null) { var go = new GameObject("World Camera"); camera = go.AddComponent<Camera>(); go.tag = "MainCamera"; }
                if(camera.GetComponent<AudioListener>()==null && FindFirstObjectByType<AudioListener>()==null) camera.gameObject.AddComponent<AudioListener>();
                worldCamera=camera;camera.clearFlags=CameraClearFlags.SolidColor;camera.orthographic = true; camera.orthographicSize = 7; camera.rect=new Rect(0,.18f,1,.735f); camera.backgroundColor = new Color(.025f,.035f,.065f);
                camera.transform.position = new Vector3(15.5f, 8.5f, -10);
            }
            Player.Restore(x, y);
        }
        public void ConfirmStory(GameState state){furniture?.Confirm(state);}
        public void Emphasize(string id){area?.transform.Find(id)?.GetComponent<CityCharacter>()?.Emphasize();}
        void LateUpdate()
        {
            if(Player==null)return;
            var camera=worldCamera!=null?worldCamera:Camera.main;
            if(camera!=null){
                var ui=GetComponent<GameUI>();camera.enabled=ui==null||!ui.TitleVisible;camera.rect=ui!=null?ui.WorldViewport:new Rect(0,.18f,1,.735f);camera.aspect=(Screen.width*camera.rect.width)/(Screen.height*camera.rect.height);camera.orthographicSize=6.8f;
                float half=camera.orthographicSize,wide=half*camera.aspect;
                camera.transform.position=new Vector3(Mathf.Clamp(Player.Position.x,Mathf.Min(wide-1,15.5f),Mathf.Max(31-wide,15.5f)),Mathf.Clamp(Player.Position.y+1.8f,8.5f,18-half),-10);
            }
            WorldObject nearest=null;float distance=1.75f;
            foreach(var point in points??System.Array.Empty<WorldObject>()){float d=Vector2.Distance(Player.Position,new Vector2(point.x,point.y));if(d<=distance){nearest=point;distance=d;}}
            if(interactionHint!=null){interactionHint.text=nearest==null||(GetComponent<GameUI>()?.Blocking??false)?"":nearest.kind=="portal"?"[ E ]  Enter":nearest.kind=="npc"?"[ E ]  Talk":"[ E ]  Inspect";interactionHint.transform.position=new Vector3(Player.Position.x,Player.Position.y-.6f,0);}
            foreach(var resident in residents)if(resident!=null) {
                Vector2 toward=Player.Position-(Vector2)resident.transform.position;
                if(toward.sqrMagnitude<9)resident.Pose(toward,false);
            }
        }
        Tilemap Layer(string name, int order, bool collision)
        {
            var layer = new GameObject(name); layer.transform.SetParent(area.transform);
            layer.transform.localPosition = new Vector3(-.5f, -.5f, 0); // Tiles are centered on the server's integer cells.
            var map = layer.AddComponent<Tilemap>(); layer.AddComponent<TilemapRenderer>().sortingOrder = order;
            if (collision) layer.AddComponent<TilemapCollider2D>();
            return map;
        }
        Tile MakeTile(int index,Color color)
        {
            var tile = ScriptableObject.CreateInstance<Tile>(); tile.sprite=NightArt.Tile(index); tile.color=color;
            tile.colliderType=Tile.ColliderType.Grid; assets.Add(tile); return tile;
        }
        SpriteRenderer Prop(int index,float x,float y,Color color,int order=2)
        {
            var go=new GameObject("Urban tile "+index);go.transform.SetParent(area.transform);go.transform.position=new Vector3(x,y,0);
            var r=go.AddComponent<SpriteRenderer>();r.sprite=NightArt.Tile(index);r.color=color;r.sortingOrder=order;return r;
        }
        void DressVenue(Location location)
        {
            Color cool=new Color(.26f,.34f,.50f),warm=NightArt.Accent(location.id);
            // Only existing solid cells receive obstructive-looking architecture.
            // Walkable rows, portal approaches and all server object anchors remain clear.
            for(int y=11;y<=14;y++)for(int x=7;x<=10;x++)
                if(x<location.width&&y<location.height&&location.rows[y][x]=='1')
                    Prop(y>=13?109:(y==12?126:153),x,y,cool);
            for(int x=1;x<location.width-1;x++) {
                Prop(125,x,17,cool); Prop(x%4==0?337:109,x,18,x%4==0?warm:cool);
                if(x%4==0) Glow(x,17.5f,new Color(warm.r,warm.g,warm.b,.09f),3);
            }
            if(location.id=="quay") { Prop(303,7,11,warm,3);Prop(276,8,11,warm,3);Prop(300,9,11,warm,3);Prop(304,10,11,warm,3); }
            else if(location.id=="market") { for(int x=7;x<=10;x++)Prop(x%2==0?309:310,x,12,Color.white,3); }
            else if(location.id=="archive") { Prop(382,7,11,warm,3);Prop(383,8,11,warm,3);Prop(284,9,12,warm,3);Prop(303,10,11,warm,3); }
            else if(location.id=="station") { Prop(355,7,12,warm,3);Prop(356,8,12,warm,3);Prop(357,9,12,warm,3);Prop(358,10,12,warm,3);Glow(14,9,new Color(.9f,.68f,.35f,.1f),5); }
            for(int x=5;x<location.width-2;x+=8) {
                Prop(165,x,16,cool,4);Prop(192,x,15,cool,4);Glow(x,15.6f,new Color(1,.72f,.4f,.13f),3.5f);
            }
            VenueDetails(location.id);
            var interior=new GameObject("Furnished interior");interior.transform.SetParent(area.transform);furniture=interior.AddComponent<VenueFurniture>();furniture.Build(location);
            var rain=new GameObject("Local night rain");rain.transform.SetParent(area.transform);rain.AddComponent<NightRain>();
            var sign=new GameObject("Venue sign").AddComponent<TextMesh>();sign.transform.SetParent(area.transform);sign.transform.position=new Vector3(19,15.6f,0);
            sign.text=NightArt.Venue(location.id);sign.fontSize=64;sign.characterSize=.065f;sign.anchor=TextAnchor.MiddleCenter;sign.color=warm;sign.GetComponent<MeshRenderer>().sortingOrder=500;
        }
        void VenueDetails(string id)
        {
            // Original 16px supporting icons drawn for this game, on the existing solid storefront.
            const int n=16;var texture=new Texture2D(n,n,TextureFormat.RGBA32,false);texture.filterMode=FilterMode.Point;
            var pixels=new Color[n*n];Color accent=NightArt.Accent(id);
            for(int y=0;y<n;y++)for(int x=0;x<n;x++) {
                float d=Vector2.Distance(new Vector2(x,y),new Vector2(7.5f,7.5f));
                if(id=="quay" && d<7) pixels[y*n+x]=d<2?accent:new Color(.04f,.06f,.1f);
                if(id=="market" && x>1&&x<14&&y>2&&y<13) pixels[y*n+x]=(x>3&&x<12&&y>4&&y<11)?new Color(.78f,.86f,.87f):new Color(.1f,.15f,.23f);
                if(id=="archive" && y>2&&y<13&&Mathf.Abs(x-7.5f)<(y>9?5:3)) pixels[y*n+x]=accent;
                if(id=="station" && Mathf.Abs(x-7.5f)<2 && y>1&&y<15) pixels[y*n+x]=new Color(1,.83f,.50f);
            }
            texture.SetPixels(pixels);texture.Apply();var sprite=Sprite.Create(texture,new Rect(0,0,n,n),new Vector2(.5f,.5f),16);
            assets.Add(texture);assets.Add(sprite);
            for(int i=0;i<3;i++){var go=new GameObject("Original venue detail");go.transform.SetParent(area.transform);go.transform.position=new Vector3(7.5f+i,12,0);var visual=go.AddComponent<SpriteRenderer>();visual.sprite=sprite;visual.sortingOrder=4;}
        }
        void Shadow(float x,float y) { Glow(x,y-.03f,new Color(.01f,.02f,.04f,.45f),.8f); }
        void Glow(float x,float y,Color color,float size)
        {
            // Original radial supporting effect, not borrowed game art. Built-in alpha blending works in WebGL.
            const int n=32;var texture=new Texture2D(n,n,TextureFormat.RGBA32,false);texture.filterMode=FilterMode.Bilinear;
            var pixels=new Color[n*n];for(int iy=0;iy<n;iy++)for(int ix=0;ix<n;ix++){float d=Vector2.Distance(new Vector2(ix,iy),new Vector2(15.5f,15.5f))/16;pixels[iy*n+ix]=new Color(1,1,1,Mathf.Pow(Mathf.Max(0,1-d),2));}
            texture.SetPixels(pixels);texture.Apply();var sprite=Sprite.Create(texture,new Rect(0,0,n,n),new Vector2(.5f,.5f),n);
            var go=new GameObject("Light pool");go.transform.SetParent(area.transform);go.transform.position=new Vector3(x,y,0);go.transform.localScale=new Vector3(size,size*.55f,1);
            var r=go.AddComponent<SpriteRenderer>();r.sprite=sprite;r.color=color;r.sortingOrder=5;go.AddComponent<NightPulse>();assets.Add(texture);assets.Add(sprite);
        }
        public void Clear()
        {
            if (area != null) { area.SetActive(false); Destroy(area); }
            foreach (Object asset in assets) if (asset != null) Destroy(asset);
            assets.Clear();residents.Clear(); Player = null; LocationId = null;
        }
        void OnDestroy() { if(worldCamera!=null)worldCamera.enabled=true;Clear(); }
    }
}
