using UnityEngine;

namespace InfiniteStories
{
    [RequireComponent(typeof(Rigidbody2D), typeof(CircleCollider2D), typeof(SpriteRenderer))]
    public sealed class PlayerMotor : MonoBehaviour
    {
        public bool CanMove { get; set; }
        public float Speed { get; set; } = 3f;
        Rigidbody2D body;
        SpriteRenderer visual;
        CityCharacter character;
        Vector2 input;
        Vector2 accessibleDirection;
        float accessibleRemaining;
        public Vector2 Position => body != null ? body.position : (Vector2)transform.position;
        void Awake()
        {
            body = GetComponent<Rigidbody2D>(); body.gravityScale = 0; body.freezeRotation = true;
            body.interpolation = RigidbodyInterpolation2D.Interpolate; body.collisionDetectionMode = CollisionDetectionMode2D.Continuous;
            GetComponent<CircleCollider2D>().radius = 0.28f;
            visual = GetComponent<SpriteRenderer>(); visual.sortingOrder = 20;
            character = gameObject.AddComponent<CityCharacter>(); character.Actor=0; character.Pose(Vector2.zero,false);
        }
        void Update()
        {
            Vector2 direction = accessibleRemaining > 0 ? accessibleDirection :
                new Vector2(Input.GetAxisRaw("Horizontal"), Input.GetAxisRaw("Vertical"));
            input = CanMove ? direction.normalized : Vector2.zero;
            character.Pose(input,input.sqrMagnitude > 0);
        }
        void FixedUpdate()
        {
            if (CanMove && accessibleRemaining>0)
            {
                body.linearVelocity=accessibleDirection*Speed;
                accessibleRemaining=Mathf.Max(0,accessibleRemaining-Time.fixedDeltaTime);
                if (accessibleRemaining==0) input=Vector2.zero;
            }
            else body.linearVelocity=CanMove ? input*Speed : Vector2.zero;
        }
        // Accessible buttons use the same physics controller and collision path as keys.
        public void Nudge(Vector2 direction) { accessibleDirection=direction.normalized; accessibleRemaining=.32f; }
        public void StopInput() { accessibleRemaining=0; input=Vector2.zero; if (body!=null) body.linearVelocity=Vector2.zero; }
        public void Restore(float x, float y) { body.position = new Vector2(x, y); body.linearVelocity = Vector2.zero; }
    }
}
