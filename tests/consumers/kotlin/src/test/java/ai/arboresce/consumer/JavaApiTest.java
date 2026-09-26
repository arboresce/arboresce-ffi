package ai.arboresce.consumer;

import ai.arboresce.Arboresce;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class JavaApiTest {
    @Test
    void publicStaticFacade() throws ReflectiveOperationException {
        assertEquals("Arboresce", Arboresce.NAME);
        assertEquals("Arboresce", Arboresce.name());
        assertEquals(String.class, Arboresce.class.getMethod("name").getReturnType());
        assertEquals(void.class, Arboresce.class.getMethod("printName").getReturnType());
        for (Method method : Arboresce.class.getDeclaredMethods()) {
            if (Modifier.isPublic(method.getModifiers())) {
                assertTrue(Modifier.isStatic(method.getModifiers()));
                assertFalse(method.getReturnType().getName().startsWith("com.sun.jna."));
                for (Class<?> parameter : method.getParameterTypes()) {
                    assertFalse(parameter.getName().startsWith("com.sun.jna."));
                }
            }
        }
    }
}
